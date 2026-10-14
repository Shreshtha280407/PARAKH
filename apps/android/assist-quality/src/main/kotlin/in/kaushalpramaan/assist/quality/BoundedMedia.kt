package `in`.kaushalpramaan.assist.quality

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.MediaMetadataRetriever
import android.os.Build
import androidx.exifinterface.media.ExifInterface
import java.io.File
import java.io.Closeable

class MediaFailure(val code: String) : Exception(code)
data class VideoInfo(val durationMs: Long, val encodedWidth: Int, val encodedHeight: Int, val rotationDegrees: Int) {
    val displayWidth: Int get() = if (rotationDegrees % 180 == 0) encodedWidth else encodedHeight
    val displayHeight: Int get() = if (rotationDegrees % 180 == 0) encodedHeight else encodedWidth
}

/** Read-only adapters. Call on a background dispatcher. Caller owns returned bitmaps.
 * Source duration and dimensions are capped; at most one returned video bitmap is owned at
 * a time. Android's codec still owns its native decode buffers. No media is rewritten.
 */
object BoundedMedia {
    const val LONGEST_EDGE = 320
    const val MAX_SOURCE_PIXELS = 50_000_000L

    fun photo(file: File, longestEdge: Int = LONGEST_EDGE): Bitmap {
        require(longestEdge in 32..640)
        if (!file.isFile) throw MediaFailure("missing_input")
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.absolutePath, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) throw MediaFailure("unsupported_or_corrupt_image")
        if (bounds.outWidth.toLong() * bounds.outHeight > MAX_SOURCE_PIXELS) throw MediaFailure("source_dimensions_limit")
        var sample = 1
        while (maxOf(bounds.outWidth, bounds.outHeight) / sample > longestEdge * 2) sample *= 2
        val options = BitmapFactory.Options().apply {
            inSampleSize = sample; inPreferredConfig = Bitmap.Config.ARGB_8888; inScaled = false
        }
        var bitmap = BitmapFactory.decodeFile(file.absolutePath, options) ?: throw MediaFailure("image_decode_failed")
        try {
            val orientation = ExifInterface(file).getAttributeInt(ExifInterface.TAG_ORIENTATION, 1)
            val oriented = orient(bitmap, orientation)
            if (oriented !== bitmap) { bitmap.recycle(); bitmap = oriented }
            val scaled = scale(bitmap, longestEdge)
            if (scaled !== bitmap) bitmap.recycle()
            return scaled
        } catch (failure: Throwable) { bitmap.recycle(); throw failure }
    }

    fun orient(bitmap: Bitmap, exif: Int): Bitmap {
        val matrix = Matrix()
        when (exif) {
            2 -> matrix.setScale(-1f, 1f)
            3 -> matrix.setRotate(180f)
            4 -> matrix.setScale(1f, -1f)
            5 -> { matrix.setRotate(90f); matrix.postScale(-1f, 1f) }
            6 -> matrix.setRotate(90f)
            7 -> { matrix.setRotate(-90f); matrix.postScale(-1f, 1f) }
            8 -> matrix.setRotate(-90f)
            else -> return bitmap
        }
        return Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
    }

    fun scale(bitmap: Bitmap, longestEdge: Int): Bitmap {
        val longest = maxOf(bitmap.width, bitmap.height)
        if (longest <= longestEdge) return bitmap
        val w = maxOf(1, (bitmap.width.toLong() * longestEdge / longest).toInt())
        val h = maxOf(1, (bitmap.height.toLong() * longestEdge / longest).toInt())
        return Bitmap.createScaledBitmap(bitmap, w, h, true)
    }

    fun gray(bitmap: Bitmap): GrayFrame {
        require(maxOf(bitmap.width, bitmap.height) <= 640)
        val row = IntArray(bitmap.width)
        val bytes = ByteArray(bitmap.width * bitmap.height)
        for (y in 0 until bitmap.height) {
            bitmap.getPixels(row, 0, bitmap.width, 0, y, bitmap.width, 1)
            for (x in row.indices) bytes[y * bitmap.width + x] = QualityMetrics.luma(row[x]).toByte()
        }
        return GrayFrame(bitmap.width, bitmap.height, bytes)
    }
}

class VideoFrames(private val file: File, private val useSequentialDecoder: Boolean = true) : Closeable {
    private val retriever = MediaMetadataRetriever()
    private var sequential: SequentialVideoDecoder? = null
    val info: VideoInfo
    init {
        try {
            retriever.setDataSource(file.absolutePath)
            fun number(key: Int) = retriever.extractMetadata(key)?.toLongOrNull() ?: throw MediaFailure("invalid_video_metadata")
            val duration = number(MediaMetadataRetriever.METADATA_KEY_DURATION)
            val w = number(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH).toInt()
            val h = number(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT).toInt()
            val rotation = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION)?.toIntOrNull() ?: 0
            if (duration !in 1..SampleTimes.MAX_DURATION_MS || w !in 1..4096 || h !in 1..4096 ||
                w.toLong() * h > 9_000_000 || rotation !in listOf(0, 90, 180, 270)) throw MediaFailure("video_limits_or_rotation")
            info = VideoInfo(duration, w, h, rotation)
        } catch (failure: Throwable) { retriever.release(); throw failure }
    }
    /** Requested source-relative milliseconds, not wall time. Default sequential decoding
     * selects the first frame at/after the request (or an EOS candidate <=100ms before it).
     * The platform comparison path returns a nearby frame with rotation already baked.
     * Each path applies container rotation exactly once; device fixtures compare pixels.
     */
    fun frame(timestampMs: Long, longestEdge: Int = BoundedMedia.LONGEST_EDGE, checkCancellation: () -> Unit = {}): Bitmap? {
        require(timestampMs in 0 until info.durationMs && longestEdge in 32..640)
        if (Build.VERSION.SDK_INT < 27 || useSequentialDecoder) {
            val decoder = sequential ?: SequentialVideoDecoder(file, info).also { sequential = it }
            return decoder.frame(timestampMs, longestEdge, checkCancellation)
        }
        val decoded = retriever.getScaledFrameAtTime(timestampMs * 1000,
            MediaMetadataRetriever.OPTION_CLOSEST, longestEdge, longestEdge) ?: return null
        var result = BoundedMedia.scale(decoded, longestEdge)
        if (result !== decoded) decoded.recycle()
        if (result.config != Bitmap.Config.ARGB_8888) {
            val converted = result.copy(Bitmap.Config.ARGB_8888, false)
            result.recycle()
            result = converted ?: throw MediaFailure("argb_conversion_failed")
        }
        return result
    }
    override fun close() { try { sequential?.close() } finally { retriever.release() } }
}
