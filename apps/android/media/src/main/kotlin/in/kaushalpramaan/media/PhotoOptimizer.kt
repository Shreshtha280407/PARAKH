package `in`.kaushalpramaan.media

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import androidx.exifinterface.media.ExifInterface
import java.io.File
import java.io.FileOutputStream

sealed class PhotoOptimizationResult {
    /** The captured file already fit [PhotoOptimizer.optimize]'s target -- returned completely
     * untouched (same [File], same bytes). Never recompressed merely for the sake of it. */
    data class KeptAsIs(val file: File, val bytes: Long) : PhotoOptimizationResult()

    /** Resized/recompressed to fit, at [qualityUsed] (85 or the 75 floor). */
    data class Optimized(val file: File, val bytes: Long, val widthPx: Int, val heightPx: Int, val qualityUsed: Int) :
        PhotoOptimizationResult()

    /** Even at 1600px/quality-75 the photo cannot fit [PhotoOptimizer.optimize]'s target.
     * [bestAttemptFile] is the real floor-quality output, deliberately NOT deleted -- a
     * recoverable draft the caller can show the worker before they retake/replace/remove. */
    data class QualityFloorExceeded(val bestAttemptFile: File, val bestAttemptBytes: Long) : PhotoOptimizationResult()

    /** [PhotoOptimizer.validateDecodable] failed -- not a valid/openable image at all. */
    data object UndecodablePhoto : PhotoOptimizationResult()
}

/**
 * Local, RAM-safe photo optimisation (P5 spec part C). Never loads a full-resolution bitmap
 * into memory unless a resize pass is actually needed (decode uses [BitmapFactory.Options]'
 * `inSampleSize`, computed from bounds-only decode, the same RAM-safe technique
 * `CaptureSession.decodeBoundsOnly` already uses elsewhere in this codebase for P4).
 */
class PhotoOptimizer {

    /** Bounds-only decode -- never loads pixel data -- so this is safe to call on an
     * arbitrarily large or corrupt file before deciding whether to do anything else with it. */
    fun validateDecodable(file: File): Boolean {
        val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.absolutePath, options)
        return options.outWidth > 0 && options.outHeight > 0
    }

    /**
     * If [sourceFile] already fits within [targetBytes], returns it byte-identical. Otherwise
     * resizes the longest side to at most [MAX_LONGEST_SIDE_PX], tries JPEG quality
     * [QUALITY_FIRST] then the [QUALITY_FLOOR] minimum, preserves orientation (baked into
     * pixels, not left as an EXIF tag downstream consumers might ignore), and writes the
     * result into [outputDir]. Never destroys the only copy: on [PhotoOptimizationResult
     * .QualityFloorExceeded] the floor-quality attempt is kept on disk, not deleted.
     */
    fun optimize(sourceFile: File, targetBytes: Long, outputDir: File): PhotoOptimizationResult {
        if (!validateDecodable(sourceFile)) return PhotoOptimizationResult.UndecodablePhoto

        val sourceBytes = sourceFile.length()
        if (sourceBytes <= targetBytes) {
            return PhotoOptimizationResult.KeptAsIs(sourceFile, sourceBytes)
        }

        val orientation = readOrientation(sourceFile)
        val (boundsWidth, boundsHeight) = decodeBounds(sourceFile)
        val sampleSize = computeSampleSize(boundsWidth, boundsHeight, MAX_LONGEST_SIDE_PX)
        val sampledOptions = BitmapFactory.Options().apply { inSampleSize = sampleSize }
        val decoded = BitmapFactory.decodeFile(sourceFile.absolutePath, sampledOptions)
            ?: return PhotoOptimizationResult.UndecodablePhoto

        val rotated = applyOrientation(decoded, orientation)
        val resized = scaleToLongestSide(rotated, MAX_LONGEST_SIDE_PX)

        outputDir.mkdirs()
        try {
            val qualities = intArrayOf(QUALITY_FIRST, QUALITY_FLOOR)
            qualities.forEachIndexed { index, quality ->
                val candidate = File(outputDir, "${sourceFile.nameWithoutExtension}.opt.q$quality.jpg")
                FileOutputStream(candidate).use { out -> resized.compress(Bitmap.CompressFormat.JPEG, quality, out) }
                val bytes = candidate.length()
                val isLastAttempt = index == qualities.lastIndex
                when {
                    bytes <= targetBytes ->
                        return PhotoOptimizationResult.Optimized(candidate, bytes, resized.width, resized.height, quality)
                    isLastAttempt ->
                        return PhotoOptimizationResult.QualityFloorExceeded(candidate, bytes)
                    else ->
                        candidate.delete() // not the final attempt; will retry at the next, lower quality step
                }
            }
            error("unreachable: qualities is non-empty, the loop above always returns")
        } finally {
            if (resized !== rotated) resized.recycle()
            if (rotated !== decoded) rotated.recycle()
            decoded.recycle()
        }
    }

    private fun decodeBounds(file: File): Pair<Int, Int> {
        val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.absolutePath, options)
        return options.outWidth to options.outHeight
    }

    private fun computeSampleSize(width: Int, height: Int, maxLongestSide: Int): Int {
        var sampleSize = 1
        val longest = maxOf(width, height)
        while (longest / (sampleSize * 2) >= maxLongestSide) sampleSize *= 2
        return sampleSize
    }

    /** Visible to tests: reading an EXIF tag is pure metadata parsing, independent of (and
     * safe to test independent of) real JPEG pixel decode/encode. */
    internal fun readOrientation(file: File): Int = try {
        ExifInterface(file.absolutePath).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
    } catch (_: Exception) {
        ExifInterface.ORIENTATION_NORMAL
    }

    /** Bakes the EXIF orientation into the pixel data via a rotation/flip matrix so the
     * output JPEG is correctly oriented without relying on any downstream reader (in-app
     * preview, Media3, a future P6 server) to interpret an EXIF orientation tag. Visible to
     * tests as a pure in-memory bitmap transform, independent of file/codec I/O. */
    internal fun applyOrientation(bitmap: Bitmap, orientation: Int): Bitmap {
        val matrix = Matrix()
        when (orientation) {
            ExifInterface.ORIENTATION_ROTATE_90 -> matrix.postRotate(90f)
            ExifInterface.ORIENTATION_ROTATE_180 -> matrix.postRotate(180f)
            ExifInterface.ORIENTATION_ROTATE_270 -> matrix.postRotate(270f)
            ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> matrix.postScale(-1f, 1f)
            ExifInterface.ORIENTATION_FLIP_VERTICAL -> matrix.postScale(1f, -1f)
            ExifInterface.ORIENTATION_TRANSPOSE -> {
                matrix.postRotate(90f)
                matrix.postScale(-1f, 1f)
            }
            ExifInterface.ORIENTATION_TRANSVERSE -> {
                matrix.postRotate(270f)
                matrix.postScale(-1f, 1f)
            }
            else -> return bitmap
        }
        return Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
    }

    private fun scaleToLongestSide(bitmap: Bitmap, maxLongestSide: Int): Bitmap {
        val longest = maxOf(bitmap.width, bitmap.height)
        if (longest <= maxLongestSide) return bitmap
        val scale = maxLongestSide.toFloat() / longest
        val newWidth = (bitmap.width * scale).toInt().coerceAtLeast(1)
        val newHeight = (bitmap.height * scale).toInt().coerceAtLeast(1)
        return Bitmap.createScaledBitmap(bitmap, newWidth, newHeight, true)
    }

    companion object {
        const val MAX_LONGEST_SIDE_PX = 1600
        const val QUALITY_FIRST = 85
        const val QUALITY_FLOOR = 75
    }
}
