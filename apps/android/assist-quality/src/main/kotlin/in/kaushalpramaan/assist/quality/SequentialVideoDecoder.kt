package `in`.kaushalpramaan.assist.quality

import android.graphics.Bitmap
import android.graphics.ImageFormat
import android.media.Image
import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaExtractor
import android.media.MediaFormat
import java.io.Closeable
import java.io.File

/** Sequential hardware decode on API26+, with only
 * selected YUV frames materialized as <=640px RGB; no full-resolution Bitmap or frame tree.
 * Nearest-neighbour YUV sampling and explicit limited/full-range SDR conversion differ
 * from the optional API27+ platform RGB comparison scaler. Calibration uses this actual
 * default path. Intermediate inter-frame codec buffers are native.
 */
internal class SequentialVideoDecoder(file: File, private val info: VideoInfo) : Closeable {
    private val extractor = MediaExtractor()
    private var codec: MediaCodec? = null
    private var inputEnded = false
    private var outputEnded = false
    private var lastRequest = -1L
    private var standard = MediaFormat.COLOR_STANDARD_BT601_NTSC
    private var fullRange = false
    private var yuvToRgb = YuvToRgb(ColorStandard.BT601, false)
    init {
        try {
            extractor.setDataSource(file.absolutePath)
            val track = (0 until extractor.trackCount).firstOrNull {
                extractor.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("video/") == true
            } ?: throw MediaFailure("missing_video_track")
            extractor.selectTrack(track)
            val format = extractor.getTrackFormat(track)
            val transfer = if (format.containsKey(MediaFormat.KEY_COLOR_TRANSFER)) format.getInteger(MediaFormat.KEY_COLOR_TRANSFER) else 0
            if (transfer == MediaFormat.COLOR_TRANSFER_ST2084 || transfer == MediaFormat.COLOR_TRANSFER_HLG)
                throw MediaFailure("legacy_hdr_conversion_unavailable")
            standard = if (format.containsKey(MediaFormat.KEY_COLOR_STANDARD)) format.getInteger(MediaFormat.KEY_COLOR_STANDARD)
                else if (info.encodedHeight >= 720) MediaFormat.COLOR_STANDARD_BT709 else MediaFormat.COLOR_STANDARD_BT601_NTSC
            fullRange = format.containsKey(MediaFormat.KEY_COLOR_RANGE) && format.getInteger(MediaFormat.KEY_COLOR_RANGE) == MediaFormat.COLOR_RANGE_FULL
            yuvToRgb = YuvToRgb(when (standard) {
                MediaFormat.COLOR_STANDARD_BT709 -> ColorStandard.BT709
                MediaFormat.COLOR_STANDARD_BT2020 -> ColorStandard.BT2020
                else -> ColorStandard.BT601
            }, fullRange)
            format.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420Flexible)
            // Byte-buffer/Image output is explicitly encoded orientation, then rotated below.
            format.setInteger(MediaFormat.KEY_ROTATION, 0)
            val native = MediaCodec.createDecoderByType(format.getString(MediaFormat.KEY_MIME)!!)
            codec = native
            native.configure(format, null, null, 0); native.start()
        } catch (failure: Throwable) {
            runCatching { close() }.exceptionOrNull()?.let { failure.addSuppressed(it) }
            throw failure
        }
    }

    fun frame(timestampMs: Long, edge: Int, checkCancellation: () -> Unit): Bitmap? {
        require(timestampMs > lastRequest) { "Sequential decoder timestamps must strictly increase" }
        lastRequest = timestampMs
        val native = codec ?: throw MediaFailure("decoder_closed")
        val bufferInfo = MediaCodec.BufferInfo()
        val deadline = System.nanoTime() + 10_000_000_000L
        var candidate: Bitmap? = null
        try {
            while (!outputEnded && System.nanoTime() < deadline) {
                checkCancellation()
                if (!inputEnded) {
                    val index = native.dequeueInputBuffer(1000)
                    if (index >= 0) {
                        val input = native.getInputBuffer(index) ?: throw MediaFailure("missing_decoder_input")
                        input.clear()
                        val size = extractor.readSampleData(input, 0)
                        if (size < 0) {
                            inputEnded = true; native.queueInputBuffer(index, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                        } else {
                            native.queueInputBuffer(index, 0, size, extractor.sampleTime, 0); extractor.advance()
                        }
                    }
                }
                val output = native.dequeueOutputBuffer(bufferInfo, 1000)
                if (output >= 0) {
                    val eof = bufferInfo.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0
                    try {
                        if (bufferInfo.size > 0 && bufferInfo.presentationTimeUs >= timestampMs * 1000 - 100_000) {
                            val image = native.getOutputImage(output) ?: throw MediaFailure("decoder_yuv_unavailable")
                            val bitmap = try { convert(image, edge) } finally { image.close() }
                            candidate?.recycle(); candidate = bitmap
                            if (bufferInfo.presentationTimeUs >= timestampMs * 1000) {
                                outputEnded = eof
                                return candidate.also { candidate = null }
                            }
                        }
                    } finally { native.releaseOutputBuffer(output, false) }
                    outputEnded = eof
                }
            }
            if (!outputEnded) throw MediaFailure("video_decode_timeout")
            return candidate.also { candidate = null }
        } finally { candidate?.recycle() }
    }

    private fun convert(image: Image, edge: Int): Bitmap {
        val planes = image.planes
        if (image.format != ImageFormat.YUV_420_888 || planes.size != 3) throw MediaFailure("unsupported_decoder_pixel_format")
        val crop = image.cropRect; val longest = maxOf(crop.width(), crop.height())
        val w = maxOf(1, crop.width() * minOf(edge, longest) / longest)
        val h = maxOf(1, crop.height() * minOf(edge, longest) / longest)
        val pixels = IntArray(w * h)
        val buffers = planes.map { it.buffer }
        val positions = buffers.map { it.position() }
        fun channel(index: Int, x: Int, y: Int): Int = buffers[index].get(
            positions[index] + y * planes[index].rowStride + x * planes[index].pixelStride).toInt() and 255
        for (y in 0 until h) for (x in 0 until w) {
            val sx = crop.left + minOf(crop.width() - 1, (2 * x + 1) * crop.width() / (2 * w))
            val sy = crop.top + minOf(crop.height() - 1, (2 * y + 1) * crop.height() / (2 * h))
            pixels[y * w + x] = yuvToRgb.argb(channel(0, sx, sy), channel(1, sx / 2, sy / 2), channel(2, sx / 2, sy / 2))
        }
        val bitmap = Bitmap.createBitmap(pixels, w, h, Bitmap.Config.ARGB_8888)
        try {
            val oriented = BoundedMedia.orient(bitmap, when (info.rotationDegrees) { 90 -> 6; 180 -> 3; 270 -> 8; else -> 1 })
            if (oriented !== bitmap) bitmap.recycle()
            return oriented
        } catch (failure: Throwable) { bitmap.recycle(); throw failure }
    }
    override fun close() {
        val native = codec; codec = null
        try { if (native != null) { try { native.stop() } finally { native.release() } } }
        finally { extractor.release() }
    }
}
