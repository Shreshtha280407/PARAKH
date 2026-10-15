package `in`.kaushalpramaan.assist.quality

import android.content.Context
import java.io.File
import java.security.MessageDigest
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import org.json.JSONObject

enum class AnalysisStatus { SUCCESS, PARTIAL, FAILED, UNAVAILABLE }
enum class QualityCondition { DARK, OVEREXPOSED, BLURRY, CAMERA_MOTION }
data class QualityFlag(val condition: QualityCondition, val severity: String = "review",
    val observed: Double, val threshold: Double)
data class QualitySample(val timestampMs: Long, val metrics: ImageMetrics?, val motion: MotionMetrics?,
    val flags: List<QualityFlag>, val error: String?, val decodeMs: Double, val calculationMs: Double)
data class QualityResult(val status: AnalysisStatus, val moduleVersion: String,
    val thresholdVersion: String?, val thresholdSha256: String?, val thresholdCalibrated: Boolean,
    val durationMs: Long?, val samples: List<QualitySample>, val intervals: Map<QualityCondition, List<TimeRange>>,
    val analysedSampleCount: Int, val requestedSampleCount: Int, val analysedDurationMs: Long,
    val motionAnalysedPairCount: Int, val motionRequestedPairCount: Int, val wallTimeMs: Double, val error: String?,
    /** Combined review-worthy hint derived from the same disclosed flags/intervals; null when
     * unavailable (uncalibrated or no valid sample). Never a competence/pass-fail judgement,
     * and never blocks evidence submission. See [QualityVerdict]. */
    val badCapture: Boolean? = null)

/** The JSON asset is the single source of thresholds. Uncalibrated profiles can expose
 * observed metrics, but never produce accepted/calibrated quality advice. */
data class QualityThresholds(val version: String, val sha256: String, val calibrated: Boolean,
    val meanDark: Double, val meanBright: Double, val highlightFraction: Double,
    val blurVariance: Double, val motionTranslationPx: Double, val videoBlurVariance: Double = blurVariance,
    /** Clip-level aggregation policy for [QualityVerdict]; defaults reproduce the original
     * unfiltered any-single-anchor behaviour for profiles that predate this policy (v1/v2). */
    val clipBadFraction: Double = 0.2, val darkMinConsecutiveAnchors: Int = 1,
    val blurryMinConsecutiveAnchors: Int = 1, val cameraMotionCountsTowardBadCapture: Boolean = true) {
    init {
        require(version.isNotBlank() && meanDark in 0.0..255.0 && meanBright in meanDark..255.0)
        require(highlightFraction in 0.0..1.0 && blurVariance >= 0 && videoBlurVariance >= 0 && motionTranslationPx in 0.0..6.0)
        require(clipBadFraction in 0.0..1.0 && darkMinConsecutiveAnchors >= 1 && blurryMinConsecutiveAnchors >= 1)
    }
    fun flags(metrics: ImageMetrics, motion: MotionMetrics? = null, video: Boolean = false): List<QualityFlag> {
        if (!calibrated) return emptyList()
        val result = mutableListOf<QualityFlag>()
        if (metrics.meanLuma < meanDark) result += QualityFlag(QualityCondition.DARK, observed = metrics.meanLuma, threshold = meanDark)
        if (metrics.meanLuma > meanBright && metrics.highlightClipFraction > highlightFraction)
            result += QualityFlag(QualityCondition.OVEREXPOSED, observed = metrics.highlightClipFraction, threshold = highlightFraction)
        // Underexposure also reduces Laplacian variance; do not call unobservable detail defocus.
        val blurThreshold = if (video) videoBlurVariance else blurVariance
        if (metrics.meanLuma >= meanDark && metrics.laplacianVariance != null && metrics.laplacianVariance < blurThreshold)
            result += QualityFlag(QualityCondition.BLURRY, observed = metrics.laplacianVariance, threshold = blurThreshold)
        if (motion?.reliable == true && motion.translationPx >= motionTranslationPx)
            result += QualityFlag(QualityCondition.CAMERA_MOTION, observed = motion.translationPx, threshold = motionTranslationPx)
        return result
    }
    companion object {
        fun fromJson(bytes: ByteArray): QualityThresholds {
            val json = JSONObject(bytes.toString(Charsets.UTF_8))
            require(json.getString("metric_definition") == QualityMetrics.DEFINITION_VERSION)
            require(json.getString("motion_definition") == CameraMotion.DEFINITION_VERSION)
            require(json.getInt("longest_edge_px") == BoundedMedia.LONGEST_EDGE)
            require(json.getJSONObject("clipping").getInt("dark_inclusive") == 16)
            require(json.getJSONObject("clipping").getInt("highlight_inclusive") == 235)
            val thresholds = json.getJSONObject("thresholds")
            val hash = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
            val aggregation = json.optJSONObject("aggregation")
            return QualityThresholds(json.getString("version"), hash, json.getString("calibration_status") == "calibrated",
                thresholds.getDouble("mean_dark_below"), thresholds.getDouble("mean_bright_above"),
                thresholds.getDouble("highlight_fraction_above"), thresholds.getDouble("laplacian_variance_below"),
                thresholds.getDouble("motion_translation_px_at_least"),
                thresholds.optDouble("video_laplacian_variance_below", thresholds.getDouble("laplacian_variance_below")),
                json.optDouble("clip_bad_fraction", 0.2),
                aggregation?.optInt("dark_min_consecutive_anchors", 1) ?: 1,
                aggregation?.optInt("blurry_min_consecutive_anchors", 1) ?: 1,
                aggregation?.optBoolean("camera_motion_counts_toward_bad_capture", true) ?: true)
        }
        fun bundled(context: Context): QualityThresholds = context.assets.open("quality/thresholds.json").use { fromJson(it.readBytes()) }
    }
}

class QualityAnalyzer(private val thresholds: QualityThresholds?) {
    suspend fun photo(file: File, onGray: ((GrayFrame) -> Unit)? = null): QualityResult = withContext(Dispatchers.Default) {
        val start = System.nanoTime()
        val thresholds = thresholds ?: return@withContext unavailable(start)
        try {
            currentCoroutineContext().ensureActive()
            val beforeDecode = System.nanoTime()
            val bitmap = BoundedMedia.photo(file)
            val decodeMs = elapsed(beforeDecode)
            val sample = try {
                val beforeCalculation = System.nanoTime()
                val gray = BoundedMedia.gray(bitmap)
                onGray?.invoke(gray)
                val metrics = QualityMetrics.calculate(gray)
                QualitySample(0, metrics, null, thresholds.flags(metrics), null, decodeMs, elapsed(beforeCalculation))
            } finally { bitmap.recycle() }
            currentCoroutineContext().ensureActive()
            result(start, null, listOf(sample), 1)
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) { failed(start, failure) }
        catch (_: OutOfMemoryError) { failed(start, MediaFailure("memory_pressure")) }
    }

    suspend fun video(file: File, onSample: ((QualitySample) -> Unit)? = null): QualityResult = withContext(Dispatchers.Default) {
        val start = System.nanoTime()
        val thresholds = thresholds ?: return@withContext unavailable(start)
        val analysed = try {
            currentCoroutineContext().ensureActive()
            VideoFrames(file).use { source ->
                val cancellationContext = currentCoroutineContext()
                val samples = mutableListOf<QualitySample>()
                var previous: GrayFrame? = null
                for (time in SampleTimes.quality(source.info.durationMs)) {
                    currentCoroutineContext().ensureActive()
                    val beforeDecode = System.nanoTime()
                    var decodeMs = 0.0
                    try {
                        val bitmap = source.frame(time, checkCancellation = { cancellationContext.ensureActive() }) ?: throw MediaFailure("video_frame_decode_failed")
                        decodeMs = elapsed(beforeDecode)
                        try {
                            val beforeCalculation = System.nanoTime()
                            val gray = BoundedMedia.gray(bitmap)
                            val metrics = QualityMetrics.calculate(gray)
                            val small = QualityMetrics.motionFrame(gray)
                            // Only the close 125ms partner is used; no 1-second frame difference called shake.
                            val motion = if (time % 1000 == 125L && previous != null && small != null)
                                CameraMotion.measure(previous, small) else null
                            previous = if (time % 1000 == 0L) small else null
                            samples += QualitySample(time, metrics, motion, thresholds.flags(metrics, motion, video = true), null, decodeMs, elapsed(beforeCalculation))
                        } finally { bitmap.recycle() }
                    } catch (cancelled: CancellationException) { throw cancelled }
                    catch (failure: Exception) {
                        previous = null
                        samples += QualitySample(time, null, null, emptyList(), errorCode(failure),
                            if (decodeMs == 0.0) elapsed(beforeDecode) else decodeMs, 0.0)
                    }
                    onSample?.invoke(samples.last())
                    currentCoroutineContext().ensureActive()
                }
                currentCoroutineContext().ensureActive()
                result(start, source.info.durationMs, samples, samples.size)
            }
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) { failed(start, failure) }
        catch (_: OutOfMemoryError) { failed(start, MediaFailure("memory_pressure")) }
        analysed.copy(wallTimeMs = elapsed(start)) // Includes reader/codec release in use{}.
    }

    private fun result(start: Long, duration: Long?, samples: List<QualitySample>, requested: Int): QualityResult {
        val thresholds = thresholds ?: return unavailable(start)
        val valid = samples.count { it.metrics != null }
        val unavailableBlur = samples.any { it.metrics != null && it.metrics.laplacianVariance == null }
        val requestedMotion = samples.count { it.timestampMs % 1000 == 125L }
        val validMotion = samples.count { it.motion?.reliable == true }
        val status = when { valid == 0 -> AnalysisStatus.FAILED
            !thresholds.calibrated || valid != requested || validMotion != requestedMotion || unavailableBlur -> AnalysisStatus.PARTIAL
            else -> AnalysisStatus.SUCCESS }
        val intervalMap = if (duration == null) emptyMap() else QualityCondition.entries.associateWith { condition ->
            val primary = samples.filter { it.timestampMs % 1000 == 0L }
            val decisions = primary.map { sample ->
                val partner = samples.firstOrNull { it.timestampMs == sample.timestampMs + 125 }
                val unavailableMotion = condition == QualityCondition.CAMERA_MOTION && partner?.motion?.reliable != true
                val flag = if (sample.metrics == null || !thresholds.calibrated || unavailableMotion) null else
                    sample.flags.any { it.condition == condition } || partner?.flags?.any { it.condition == condition } == true
                sample.timestampMs to flag
            }
            SampleTimes.intervals(decisions, duration, 1000)
        }
        val coverage = if (duration == null) 0 else samples.filter { it.timestampMs % 1000 == 0L && it.metrics != null }
            .sumOf { minOf(1000, duration - it.timestampMs) }
        return QualityResult(status, MODULE_VERSION, thresholds.version, thresholds.sha256, thresholds.calibrated,
            duration, samples, intervalMap, valid, requested, coverage, validMotion, requestedMotion, elapsed(start),
            if (!thresholds.calibrated) "thresholds_not_calibrated" else if (valid != requested) "sample_failures"
            else if (unavailableBlur) "blur_unavailable" else if (validMotion != requestedMotion) "motion_coverage_partial" else null,
            QualityVerdict.evaluate(samples, duration, thresholds))
    }
    private fun failed(start: Long, failure: Exception) = QualityResult(AnalysisStatus.FAILED, MODULE_VERSION,
        thresholds?.version, thresholds?.sha256, thresholds?.calibrated ?: false, null, emptyList(), emptyMap(), 0, 0, 0, 0, 0, elapsed(start), errorCode(failure))
    private fun unavailable(start: Long) = QualityResult(AnalysisStatus.UNAVAILABLE, MODULE_VERSION, null, null, false,
        null, emptyList(), emptyMap(), 0, 0, 0, 0, 0, elapsed(start), "thresholds_missing_or_invalid")
    companion object { const val MODULE_VERSION = "quality-technical-v1"
        fun bundled(context: Context) = QualityAnalyzer(runCatching { QualityThresholds.bundled(context) }.getOrNull())
        fun elapsed(start: Long): Double = (System.nanoTime() - start) / 1_000_000.0
        fun errorCode(error: Exception) = (error as? MediaFailure)?.code ?: "analysis_${error.javaClass.simpleName}"
    }
}
