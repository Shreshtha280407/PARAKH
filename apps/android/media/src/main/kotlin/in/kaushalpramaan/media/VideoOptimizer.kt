package `in`.kaushalpramaan.media

import android.content.Context
import android.media.MediaMetadataRetriever
import android.net.Uri
import androidx.media3.common.Effect
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.util.UnstableApi
import androidx.media3.effect.Presentation
import androidx.media3.transformer.Composition
import androidx.media3.transformer.DefaultEncoderFactory
import androidx.media3.transformer.EditedMediaItem
import androidx.media3.transformer.Effects
import androidx.media3.transformer.ExportException
import androidx.media3.transformer.ExportResult
import androidx.media3.transformer.Transformer
import androidx.media3.transformer.VideoEncoderSettings
import java.io.File
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext

sealed class VideoOptimizationResult {
    /** The captured file already fit the target -- returned completely untouched. Never
     * re-transcoded merely for the sake of it. */
    data class KeptAsIs(val file: File, val bytes: Long) : VideoOptimizationResult()

    /** One real Media3 Transformer pass produced a file that fits the target. */
    data class Optimized(
        val file: File,
        val bytes: Long,
        val durationMillis: Long,
        val widthPx: Int,
        val heightPx: Int,
    ) : VideoOptimizationResult()

    /** Even the one planned pass at the SD/quality-floor profile does not fit the target.
     * [bestAttemptFile] is the real transcoded output, deliberately NOT deleted -- a
     * recoverable draft the caller can show the worker before they retake/replace/trim/remove. */
    data class QualityFloorExceeded(val bestAttemptFile: File, val bestAttemptBytes: Long) : VideoOptimizationResult()

    /** [VideoOptimizer.validateContainer] could not read usable duration/dimensions -- not a
     * valid/openable video container at all. */
    data object InvalidContainer : VideoOptimizationResult()
}

/**
 * Local, file-to-file video optimisation via the real Media3 Transformer (P5 spec part D) --
 * never a mock/no-op path. Output is always H.264 video / AAC audio in an MP4 container, one
 * of exactly two documented resolution tiers ([VideoResolutionProfile]), decided by
 * [VideoTranscodePlanner] (bitrate reduced before resolution).
 *
 * [optimize] can be called from any coroutine context -- it internally hops onto
 * [kotlinx.coroutines.Dispatchers.Main] for the parts that use Media3 Transformer, which
 * requires its own Looper thread. It never loads video frame data into the JVM heap itself;
 * Transformer's own pipeline reads/writes file-to-file through MediaCodec.
 */
@UnstableApi
class VideoOptimizer(private val context: Context) {

    /** Reads only container metadata (duration/dimensions) via [MediaMetadataRetriever] --
     * the same RAM-safe technique `CaptureSession.readVideoMetadata` already uses elsewhere in
     * this codebase for P4 -- never decodes frame data. */
    fun validateContainer(file: File): SourceVideoInfo? {
        val retriever = MediaMetadataRetriever()
        return try {
            retriever.setDataSource(file.absolutePath)
            val duration = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull()
            val width = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH)?.toIntOrNull()
            val height = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT)?.toIntOrNull()
            if (duration == null || width == null || height == null || duration <= 0 || width <= 0 || height <= 0) {
                null
            } else {
                SourceVideoInfo(duration, width, height, file.length())
            }
        } catch (_: Exception) {
            null
        } finally {
            retriever.release()
        }
    }

    suspend fun optimize(sourceFile: File, targetBytes: Long, outputDir: File): VideoOptimizationResult {
        val info = validateContainer(sourceFile) ?: return VideoOptimizationResult.InvalidContainer
        if (info.bytes <= targetBytes) return VideoOptimizationResult.KeptAsIs(sourceFile, info.bytes)

        outputDir.mkdirs()
        val output = File(outputDir, "${sourceFile.nameWithoutExtension}.opt.mp4")
        if (output.exists()) output.delete()

        return when (val plan = VideoTranscodePlanner.plan(info, targetBytes)) {
            is TranscodePlan.CannotFit -> {
                // Still run the one best-achievable pass (SD at the quality floor) so a
                // recoverable draft exists on disk rather than giving up with nothing to show
                // the worker.
                val floorPlan = TranscodePlan.Plan(
                    VideoResolutionProfile.SD,
                    VideoTranscodePlanner.MIN_VIDEO_BITRATE_BPS_SD,
                    VideoTranscodePlanner.AUDIO_BITRATE_BPS,
                )
                runTransform(sourceFile, output, floorPlan)
                VideoOptimizationResult.QualityFloorExceeded(output, output.length())
            }
            is TranscodePlan.Plan -> {
                runTransform(sourceFile, output, plan)
                val bytes = output.length()
                if (bytes <= targetBytes) {
                    val outputInfo = validateContainer(output)
                    VideoOptimizationResult.Optimized(
                        output,
                        bytes,
                        outputInfo?.durationMs ?: info.durationMs,
                        outputInfo?.widthPx ?: plan.resolution.targetWidth,
                        outputInfo?.heightPx ?: plan.resolution.targetHeight,
                    )
                } else {
                    // The one planned pass still didn't fit -- same handling as CannotFit:
                    // keep the recoverable draft, never destroy it, let the caller decide
                    // retake/replace/trim/remove.
                    VideoOptimizationResult.QualityFloorExceeded(output, bytes)
                }
            }
        }
    }

    /** Media3's [Transformer] enforces that it is built, listened to, started, and cancelled
     * from the exact same thread (its "application thread", the one with the [android.os
     * .Looper] it captured at construction) -- `verifyApplicationThread()` throws
     * [IllegalStateException] otherwise. Rather than leaking that requirement onto every
     * caller, this hops onto [Dispatchers.Main] itself for the whole Transformer lifecycle;
     * callers of [optimize] can call it from any coroutine context. */
    /** Minimal offline trim (spec part D.5): clips [sourceFile] to [startMs]..[endMs] via the
     * same real Media3 Transformer pipeline, no bitrate/resolution/quality controls. Returns
     * null for an invalid range or an unreadable source -- the caller's existing evidence is
     * left completely untouched either way ("old evidence stays valid until edited output is
     * READY"); only on a non-null success should the caller adopt the trimmed file. */
    suspend fun trim(sourceFile: File, startMs: Long, endMs: Long, outputDir: File): File? {
        val info = validateContainer(sourceFile) ?: return null
        if (startMs < 0 || endMs <= startMs || endMs > info.durationMs) return null

        outputDir.mkdirs()
        val output = File(outputDir, "${sourceFile.nameWithoutExtension}.trim.mp4")
        if (output.exists()) output.delete()

        return withContext(Dispatchers.Main) {
            val mediaItem = MediaItem.Builder()
                .setUri(Uri.fromFile(sourceFile))
                .setClippingConfiguration(
                    MediaItem.ClippingConfiguration.Builder()
                        .setStartPositionMs(startMs)
                        .setEndPositionMs(endMs)
                        .build(),
                )
                .build()
            val editedMediaItem = EditedMediaItem.Builder(mediaItem).build()
            val transformer = Transformer.Builder(context)
                .setVideoMimeType(MimeTypes.VIDEO_H264)
                .setAudioMimeType(MimeTypes.AUDIO_AAC)
                .build()
            try {
                suspendCancellableCoroutine<Unit> { cont ->
                    transformer.addListener(object : Transformer.Listener {
                        override fun onCompleted(composition: Composition, exportResult: ExportResult) {
                            if (cont.isActive) cont.resume(Unit)
                        }

                        override fun onError(composition: Composition, exportResult: ExportResult, exportException: ExportException) {
                            if (cont.isActive) cont.resumeWithException(exportException)
                        }
                    })
                    transformer.start(editedMediaItem, output.absolutePath)
                    cont.invokeOnCancellation { transformer.cancel() }
                }
                output
            } catch (_: Exception) {
                output.delete()
                null
            }
        }
    }

    private suspend fun runTransform(source: File, output: File, plan: TranscodePlan.Plan): Unit = withContext(Dispatchers.Main) {
        val mediaItem = MediaItem.fromUri(Uri.fromFile(source))
        val videoEffects: List<Effect> = listOf(
            Presentation.createForWidthAndHeight(plan.resolution.targetWidth, plan.resolution.targetHeight, Presentation.LAYOUT_SCALE_TO_FIT),
        )
        val editedMediaItem = EditedMediaItem.Builder(mediaItem)
            .setEffects(Effects(emptyList(), videoEffects))
            .build()
        // Hardware encoders treat a bare requested bitrate as a loose quality hint (observed
        // on a real OnePlus 13R: 1.6-2.3x overshoot past the requested value) unless CBR mode
        // is explicitly requested -- without this, the planner's "one pass fits the target"
        // guarantee cannot hold against real device encoders, only against Robolectric/a
        // software reference encoder.
        val encoderFactory = DefaultEncoderFactory.Builder(context)
            .setRequestedVideoEncoderSettings(
                VideoEncoderSettings.Builder()
                    .setBitrate(plan.videoBitrateBps)
                    .setBitrateMode(android.media.MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_CBR)
                    .build(),
            )
            .build()
        val transformer = Transformer.Builder(context)
            .setVideoMimeType(MimeTypes.VIDEO_H264)
            .setAudioMimeType(MimeTypes.AUDIO_AAC)
            .setEncoderFactory(encoderFactory)
            .build()

        suspendCancellableCoroutine { cont ->
            transformer.addListener(object : Transformer.Listener {
                override fun onCompleted(composition: Composition, exportResult: ExportResult) {
                    if (cont.isActive) cont.resume(Unit)
                }

                override fun onError(composition: Composition, exportResult: ExportResult, exportException: ExportException) {
                    if (cont.isActive) cont.resumeWithException(exportException)
                }
            })
            transformer.start(editedMediaItem, output.absolutePath)
            cont.invokeOnCancellation { transformer.cancel() }
        }
    }
}
