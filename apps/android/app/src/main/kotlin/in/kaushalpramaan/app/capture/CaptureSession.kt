package `in`.kaushalpramaan.app.capture

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.media.MediaMetadataRetriever
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.core.UseCase
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.video.FallbackStrategy
import androidx.camera.video.FileOutputOptions
import androidx.camera.video.Quality
import androidx.camera.video.QualitySelector
import androidx.camera.video.Recorder
import androidx.camera.video.Recording
import androidx.camera.video.VideoCapture
import androidx.camera.video.VideoRecordEvent
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import java.io.File
import java.util.concurrent.Executor
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.suspendCancellableCoroutine

enum class CaptureMode { PHOTO, VIDEO }
enum class VideoQualityChoice(val cameraXQuality: Quality) {
    SD(Quality.SD),
    HD(Quality.HD),
}

sealed class PhotoResult {
    data class Success(val file: File, val widthPx: Int?, val heightPx: Int?) : PhotoResult()
    data class Error(val message: String) : PhotoResult()
}

sealed class VideoResult {
    data class Success(val file: File, val durationMillis: Long?, val widthPx: Int?, val heightPx: Int?) : VideoResult()
    data class Error(val message: String) : VideoResult()
}

/**
 * Thin wrapper around the real CameraX bindings (no mock capture anywhere): back camera,
 * Preview + ImageCapture or Preview + VideoCapture<Recorder> bound to the capture screen's
 * own lifecycle, so rotation/backgrounding/screen-exit unbind cleanly through CameraX's own
 * lifecycle awareness rather than hand-rolled teardown logic. Writes land directly on the
 * File the caller supplies (the repository's staging file) -- CameraX never touches
 * MediaStore/Gallery.
 */
class CaptureSession(private val context: Context, private val lifecycleOwner: LifecycleOwner) {

    private val mainExecutor: Executor = ContextCompat.getMainExecutor(context)
    private var provider: ProcessCameraProvider? = null
    private var imageCapture: ImageCapture? = null
    private var videoCapture: VideoCapture<Recorder>? = null
    private var activeRecording: Recording? = null

    suspend fun bind(previewView: PreviewView, mode: CaptureMode, quality: VideoQualityChoice): Result<Unit> = try {
        val camProvider = ProcessCameraProvider.getInstance(context).awaitListenable(mainExecutor)
        provider = camProvider
        camProvider.unbindAll()

        val previewUseCase = Preview.Builder().build().also { it.surfaceProvider = previewView.surfaceProvider }
        val useCases = mutableListOf<UseCase>(previewUseCase)

        when (mode) {
            CaptureMode.PHOTO -> {
                val capture = ImageCapture.Builder().build()
                imageCapture = capture
                useCases += capture
            }
            CaptureMode.VIDEO -> {
                val qualitySelector = QualitySelector.from(
                    quality.cameraXQuality,
                    FallbackStrategy.lowerQualityOrHigherThan(quality.cameraXQuality),
                )
                val recorder = Recorder.Builder().setQualitySelector(qualitySelector).build()
                val capture = VideoCapture.withOutput(recorder)
                videoCapture = capture
                useCases += capture
            }
        }

        camProvider.bindToLifecycle(lifecycleOwner, CameraSelector.DEFAULT_BACK_CAMERA, *useCases.toTypedArray())
        Result.success(Unit)
    } catch (e: Exception) {
        Result.failure(e)
    }

    fun takePhoto(outputFile: File, onResult: (PhotoResult) -> Unit) {
        val capture = imageCapture ?: run { onResult(PhotoResult.Error("camera not ready")); return }
        val options = ImageCapture.OutputFileOptions.Builder(outputFile).build()
        capture.takePicture(
            options,
            mainExecutor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(outputFileResults: ImageCapture.OutputFileResults) {
                    val bounds = decodeBoundsOnly(outputFile)
                    onResult(PhotoResult.Success(outputFile, bounds?.first, bounds?.second))
                }

                override fun onError(exception: ImageCaptureException) {
                    onResult(PhotoResult.Error(exception.message ?: "image capture failed"))
                }
            },
        )
    }

    /** [onBytesRecorded] fires on every CameraX status tick so the caller can stop once the
     * safety ceiling is reached; [onFinalized] fires exactly once when the clip is closed,
     * whether by an explicit [stopRecording] call or an internal CameraX error. */
    fun startVideoRecording(
        outputFile: File,
        recordAudio: Boolean,
        onBytesRecorded: (Long) -> Unit,
        onFinalized: (VideoResult) -> Unit,
    ) {
        val capture = videoCapture ?: run { onFinalized(VideoResult.Error("camera not ready")); return }
        val pending = capture.output.prepareRecording(context, FileOutputOptions.Builder(outputFile).build())
        // The caller only requests audio once the permission screen has already granted
        // RECORD_AUDIO, but a user can revoke a runtime permission from Settings at any
        // time while this screen is open -- re-checking here (rather than trusting the
        // caller) avoids a SecurityException crash; falling back to a silent recording
        // keeps the capture itself valid instead of failing the whole draft.
        val audioGranted = ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
        val withAudio = if (recordAudio && audioGranted) pending.withAudioEnabled() else pending
        activeRecording = withAudio.start(mainExecutor) { event ->
            when (event) {
                is VideoRecordEvent.Status -> onBytesRecorded(event.recordingStats.numBytesRecorded)
                is VideoRecordEvent.Finalize -> {
                    activeRecording = null
                    if (event.hasError()) {
                        onFinalized(VideoResult.Error("finalize error code ${event.error}"))
                    } else {
                        val meta = readVideoMetadata(outputFile)
                        onFinalized(VideoResult.Success(outputFile, meta.first, meta.second, meta.third))
                    }
                }
                else -> Unit
            }
        }
    }

    fun stopRecording() {
        activeRecording?.stop()
        activeRecording = null
    }

    fun isRecording(): Boolean = activeRecording != null

    suspend fun takePhotoAwait(outputFile: File): PhotoResult = suspendCancellableCoroutine { cont ->
        takePhoto(outputFile) { result -> if (cont.isActive) cont.resume(result) }
    }

    /** Suspends for the whole recording: [onBytesRecorded] fires on every status tick
     * (letting the caller enforce the safety ceiling by calling [stopRecording] from
     * inside that same callback) and this function only resumes once CameraX finalizes
     * the clip. Cancelling the calling coroutine stops the recording rather than leaving
     * it orphaned. */
    suspend fun recordVideoAwait(outputFile: File, recordAudio: Boolean, onBytesRecorded: (Long) -> Unit): VideoResult =
        suspendCancellableCoroutine { cont ->
            startVideoRecording(outputFile, recordAudio, onBytesRecorded = onBytesRecorded) { result ->
                if (cont.isActive) cont.resume(result)
            }
            cont.invokeOnCancellation { stopRecording() }
        }

    fun unbind() {
        stopRecording()
        provider?.unbindAll()
        imageCapture = null
        videoCapture = null
    }

    /** Reads only the bitmap bounds (BitmapFactory.Options.inJustDecodeBounds), never the
     * full pixel buffer -- safe regardless of photo resolution. */
    private fun decodeBoundsOnly(file: File): Pair<Int, Int>? {
        val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.absolutePath, options)
        if (options.outWidth <= 0 || options.outHeight <= 0) return null
        return options.outWidth to options.outHeight
    }

    /** MediaMetadataRetriever reads container metadata only -- it never decodes/loads frame
     * data, so this stays safe for arbitrarily large video files. */
    private fun readVideoMetadata(file: File): Triple<Long?, Int?, Int?> {
        val retriever = MediaMetadataRetriever()
        return try {
            retriever.setDataSource(file.absolutePath)
            val duration = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull()
            val width = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH)?.toIntOrNull()
            val height = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT)?.toIntOrNull()
            Triple(duration, width, height)
        } catch (_: Exception) {
            Triple(null, null, null)
        } finally {
            retriever.release()
        }
    }
}

/** CameraX's ProcessCameraProvider.getInstance() returns a Guava ListenableFuture; this
 * avoids pulling in the separate kotlinx-coroutines-guava dependency just for one await(). */
private suspend fun <T> com.google.common.util.concurrent.ListenableFuture<T>.awaitListenable(executor: Executor): T =
    suspendCancellableCoroutine { cont ->
        addListener(
            {
                try {
                    cont.resume(get())
                } catch (e: Exception) {
                    cont.resumeWithException(e)
                }
            },
            executor,
        )
        cont.invokeOnCancellation { cancel(false) }
    }
