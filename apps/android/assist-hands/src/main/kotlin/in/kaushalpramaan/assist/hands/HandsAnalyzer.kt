package `in`.kaushalpramaan.assist.hands

import android.content.Context
import android.graphics.Bitmap
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.core.Delegate
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.handlandmarker.HandLandmarker
import `in`.kaushalpramaan.assist.quality.AnalysisStatus
import `in`.kaushalpramaan.assist.quality.BoundedMedia
import `in`.kaushalpramaan.assist.quality.MediaFailure
import `in`.kaushalpramaan.assist.quality.QualityAnalyzer.Companion.elapsed
import `in`.kaushalpramaan.assist.quality.SampleTimes
import `in`.kaushalpramaan.assist.quality.TimeRange
import `in`.kaushalpramaan.assist.quality.VideoFrames
import java.io.File
import java.security.MessageDigest
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import org.json.JSONObject

enum class HandSampleState { ANALYSED, DECODE_FAILED, INFERENCE_FAILED, UNJUDGEABLE }
data class HandSample(val timestampMs: Long, val state: HandSampleState, val handCount: Int?,
    val decodeMs: Double, val preprocessingMs: Double, val inferenceMs: Double, val error: String?,
    val widthPx: Int? = null, val heightPx: Int? = null,
    /** One handedness-classification score per detected hand (MediaPipe exposes no separate
     * raw palm-detection score through the Tasks API); not a presence/tracking probability,
     * and not landmark/identity data. Retained only to let a future on-device collection pass
     * support a confidence-threshold grid search without re-running inference per candidate. */
    val handConfidences: List<Double> = emptyList()) {
    init { require(timestampMs >= 0)
        require(if (state == HandSampleState.ANALYSED) handCount != null && handCount in 0..2 else handCount == null)
        // Empty is always allowed (e.g. fixtures/tests that do not care about confidence); a
        // non-empty list must exactly match the detected hand count and be a valid score.
        require(handConfidences.isEmpty() || handConfidences.size == (handCount ?: 0))
        require(handConfidences.all { it in 0.0..1.0 }) }
    val handPresent: Boolean? get() = if (state == HandSampleState.ANALYSED) handCount!! > 0 else null
}
data class HandsSummary(val visibleRatio: Double?, val analysedCount: Int, val failedCount: Int,
    val unjudgeableCount: Int, val coverageFraction: Double, val coveredDurationMs: Long,
    val handsNotVisibleIntervals: List<TimeRange>)
data class HandsResult(val status: AnalysisStatus, val moduleVersion: String, val modelVersion: String,
    val modelSha256: String, val configurationSha256: String, val delegate: String, val sampleIntervalMs: Long, val durationMs: Long?,
    val samples: List<HandSample>, val summary: HandsSummary, val initializationMs: Double,
    val wallTimeMs: Double, val error: String?)

object HandAggregation {
    fun summarise(samples: List<HandSample>, durationMs: Long?, intervalMs: Long): HandsSummary {
        require(samples.zipWithNext().all { it.first.timestampMs < it.second.timestampMs })
        if (durationMs != null) require(samples.all { it.timestampMs in 0 until durationMs })
        val analysed = samples.count { it.state == HandSampleState.ANALYSED }
        val unjudgeable = samples.count { it.state == HandSampleState.UNJUDGEABLE }
        val covered = if (durationMs == null) 0 else samples.filter { it.state == HandSampleState.ANALYSED }
            .sumOf { minOf(intervalMs, durationMs - it.timestampMs) }
        val intervals = if (durationMs == null) emptyList() else SampleTimes.intervals(samples.map {
            it.timestampMs to it.handPresent?.not()
        }, durationMs, intervalMs)
        return HandsSummary(if (analysed == 0) null else samples.count { it.handPresent == true }.toDouble() / analysed,
            analysed, samples.size - analysed - unjudgeable, unjudgeable,
            if (samples.isEmpty()) 0.0 else analysed.toDouble() / samples.size, covered, intervals)
    }
}

class HandsAnalyzer(private val context: Context) {
    private val manifestBytes: ByteArray by lazy { context.assets.open("hands/model.json").use { it.readBytes() } }
    private val manifest: JSONObject by lazy {
        JSONObject(manifestBytes.toString(Charsets.UTF_8))
    }
    // The bundled model asset cannot change within this analyzer's lifetime, so verifying its
    // hash is only ever done once per instance (not once per analyse() call) regardless of how
    // many photos/videos this instance analyses. A fresh HandLandmarker is still constructed on
    // every call: MediaPipe's VIDEO running mode requires strictly increasing timestamps starting
    // at 0 per clip, so the native engine itself cannot be reused across separate clips.
    private val verifiedModelAssetPath: String by lazy {
        require(manifest.getString("delegate") in setOf("CPU", "GPU"))
        val digest = MessageDigest.getInstance("SHA-256")
        context.assets.open(manifest.getString("asset")).use { input ->
            val buffer = ByteArray(64 * 1024)
            while (true) { val count = input.read(buffer); if (count < 0) break; digest.update(buffer, 0, count) }
        }
        val hash = digest.digest().joinToString("") { "%02x".format(it) }
        if (hash != manifest.getString("sha256")) throw MediaFailure("model_hash_mismatch")
        manifest.getString("asset")
    }
    private fun engine(mode: RunningMode): HandLandmarker {
        val assetPath = verifiedModelAssetPath
        val delegate = if (manifest.getString("delegate") == "GPU") Delegate.GPU else Delegate.CPU
        return HandLandmarker.createFromOptions(context,
            HandLandmarker.HandLandmarkerOptions.builder()
                .setBaseOptions(BaseOptions.builder().setModelAssetPath(assetPath).setDelegate(delegate).build())
                .setRunningMode(mode).setNumHands(manifest.getInt("num_hands"))
                .setMinHandDetectionConfidence(manifest.getDouble("min_detection_confidence").toFloat())
                .setMinHandPresenceConfidence(manifest.getDouble("min_presence_confidence").toFloat())
                .setMinTrackingConfidence(manifest.getDouble("min_tracking_confidence").toFloat()).build())
    }

    suspend fun video(file: File, onSample: ((HandSample) -> Unit)? = null): HandsResult = analyse(file, true, onSample)
    suspend fun photo(file: File): HandsResult = analyse(file, false)

    private suspend fun analyse(file: File, video: Boolean, onSample: ((HandSample) -> Unit)? = null): HandsResult = withContext(Dispatchers.Default) {
        val started = System.nanoTime()
        var initialization = 0.0
        var native: HandLandmarker? = null
        var source: VideoFrames? = null
        var duration: Long? = null
        val samples = mutableListOf<HandSample>()
        var initializationComplete = false
        var releaseError: String? = null
        val result = try {
            currentCoroutineContext().ensureActive()
            val initStart = System.nanoTime()
            native = engine(if (video) RunningMode.VIDEO else RunningMode.IMAGE)
            initialization = elapsed(initStart)
            initializationComplete = true
            if (video) { source = VideoFrames(file); duration = source.info.durationMs }
            val interval = manifest.getLong("sample_interval_ms")
            val cancellationContext = currentCoroutineContext()
            val times = if (duration != null) SampleTimes.regular(duration, interval) else listOf(0L)
            for (timestamp in times) {
                currentCoroutineContext().ensureActive()
                val beforeDecode = System.nanoTime()
                var bitmap: Bitmap? = null
                var decode = 0.0; var preprocess = 0.0; var inference = 0.0
                var state = HandSampleState.DECODE_FAILED
                try {
                    bitmap = if (video) source!!.frame(timestamp, manifest.getInt("longest_edge_px")) { cancellationContext.ensureActive() }
                        else BoundedMedia.photo(file, manifest.getInt("longest_edge_px"))
                    if (bitmap == null) throw MediaFailure("frame_decode_failed")
                    decode = elapsed(beforeDecode)
                    if (bitmap.width < 16 || bitmap.height < 16) {
                        samples += HandSample(timestamp, HandSampleState.UNJUDGEABLE, null, decode, 0.0, 0.0, "insufficient_pixel_dimensions", bitmap.width, bitmap.height)
                        onSample?.invoke(samples.last())
                        currentCoroutineContext().ensureActive()
                        continue
                    }
                    state = HandSampleState.INFERENCE_FAILED
                    val beforePreprocess = System.nanoTime()
                    val mpImage = BitmapImageBuilder(bitmap).build()
                    preprocess = elapsed(beforePreprocess)
                    try {
                        currentCoroutineContext().ensureActive()
                        val beforeInference = System.nanoTime()
                        // One fresh VIDEO engine per clip; strictly increasing, source-relative timestamps.
                        val detection = if (video) native.detectForVideo(mpImage, timestamp) else native.detect(mpImage)
                        inference = elapsed(beforeInference)
                        currentCoroutineContext().ensureActive()
                        val confidences = detection.handedness().map { candidates -> candidates.first().score().toDouble() }
                        samples += HandSample(timestamp, HandSampleState.ANALYSED, detection.landmarks().size,
                            decode, preprocess, inference, null, bitmap.width, bitmap.height, confidences)
                    } finally { mpImage.close() }
                } catch (cancelled: CancellationException) { throw cancelled }
                catch (failure: Exception) {
                    samples += HandSample(timestamp, state, null, if (decode == 0.0) elapsed(beforeDecode) else decode,
                        preprocess, inference, (failure as? MediaFailure)?.code ?: failure.javaClass.simpleName)
                } finally { bitmap?.recycle() }
                onSample?.invoke(samples.last())
                currentCoroutineContext().ensureActive()
            }
            result(started, duration, samples, initialization, null)
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) { result(started, duration, samples, initialization,
            (failure as? MediaFailure)?.code ?: failure.javaClass.simpleName, !initializationComplete) }
        catch (_: OutOfMemoryError) { result(started, duration, samples, initialization, "memory_pressure") }
        catch (_: LinkageError) { result(started, duration, samples, initialization, "native_runtime_unavailable", true) }
        finally {
            runCatching { source?.close() }.onFailure { releaseError = "resource_release_failed" }
            runCatching { native?.close() }.onFailure { releaseError = "resource_release_failed" }
        }
        result.copy(wallTimeMs = elapsed(started),
            status = if (releaseError != null && result.status == AnalysisStatus.SUCCESS) AnalysisStatus.PARTIAL else result.status,
            error = result.error ?: releaseError)
    }

    private fun result(start: Long, duration: Long?, samples: List<HandSample>, initialization: Double,
        error: String?, unavailable: Boolean = false): HandsResult {
        val interval = runCatching { manifest.getLong("sample_interval_ms") }.getOrDefault(1000)
        val summary = HandAggregation.summarise(samples, duration, interval)
        val status = when { unavailable -> AnalysisStatus.UNAVAILABLE
            summary.analysedCount == 0 -> AnalysisStatus.FAILED
            error != null || summary.coverageFraction < 1 -> AnalysisStatus.PARTIAL
            else -> AnalysisStatus.SUCCESS }
        return HandsResult(status, runCatching { manifest.getString("module_version") }.getOrDefault("hands-presence-v1"),
            runCatching { manifest.getString("model_version") }.getOrDefault("unavailable"),
            runCatching { manifest.getString("sha256") }.getOrDefault("unavailable"),
            runCatching { MessageDigest.getInstance("SHA-256").digest(manifestBytes).joinToString("") { "%02x".format(it) } }.getOrDefault("unavailable"),
            runCatching { manifest.getString("delegate") }.getOrDefault("unavailable"), interval, duration,
            samples.toList(), summary, initialization, elapsed(start), error)
    }
}
