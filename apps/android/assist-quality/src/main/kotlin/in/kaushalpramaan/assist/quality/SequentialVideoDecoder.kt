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
 * default path. Intermediate inter-frame codec buffers are native. Requests spaced closer
 * than [SEEK_GAP_THRESHOLD_US] decode every intervening frame exactly as before (this is the
 * current 1fps/1s-anchor calibration path, unaffected); wider gaps seek to the nearest
 * preceding sync sample instead, skipping fully-intervening GOPs that would otherwise be
 * decoded and discarded unconverted.
 */
/** Process-wide diagnostic counters for where video-decode time actually goes: how many
 * decoder output buffers were produced in total (most are walked past, unconverted, purely to
 * satisfy inter-frame coding dependencies) versus how much of that time was spent specifically
 * inside YUV->RGB [SequentialVideoDecoder.convert]. Reset at the start of a measurement; not
 * part of any typed analysis result and never affects behaviour. */
object DecodeProfiling {
    var intermediateFrames = 0
    var convertNs = 0L
    fun reset() { intermediateFrames = 0; convertNs = 0L }
}

internal class SequentialVideoDecoder(file: File, private val info: VideoInfo) : Closeable {
    companion object { private const val SEEK_GAP_THRESHOLD_US = 3_000_000L }
    private val extractor = MediaExtractor()
    private var codec: MediaCodec? = null
    private var inputEnded = false
    private var outputEnded = false
    private var lastRequest = -1L
    private var lastObservedPtsUs = -1L
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
        val native = codec ?: throw MediaFailure("decoder_closed")
        // Skip-ahead: only when the gap since the last decoded position is well beyond any
        // ordinary GOP (measured ~0.9-1.0s on this collection's sources), seek to the nearest
        // preceding sync sample and flush, instead of sequentially decoding every intervening
        // frame. SEEK_GAP_THRESHOLD_US is intentionally several times larger than an observed
        // GOP so the current ~1s sampling cadence never triggers this path and is byte-for-byte
        // unaffected; it exists for configurations that sample less densely than one GOP apart,
        // where walking every intervening frame is pure waste. Frame *selection* semantics
        // (first frame at/after the request, matched below) are identical either way: seeking
        // only changes where sequential decode resumes from, never what gets selected.
        if (!outputEnded && lastObservedPtsUs >= 0 && timestampMs * 1000L - lastObservedPtsUs > SEEK_GAP_THRESHOLD_US) {
            extractor.seekTo(timestampMs * 1000L, MediaExtractor.SEEK_TO_PREVIOUS_SYNC)
            native.flush()
            inputEnded = false
        }
        lastRequest = timestampMs
        val bufferInfo = MediaCodec.BufferInfo()
        val deadline = System.nanoTime() + 10_000_000_000L
        // The exact "first frame at/after the request, or an EOS candidate <=100ms before it"
        // selection rule means every frame in [target-100ms, target) is only ever a FALLBACK,
        // used solely if the stream ends before a frame >=target ever arrives. At ~30fps that
        // window holds several frames; converting each one as it is seen (as earlier versions
        // of this decoder did) pays the full YUV->RGB cost for frames almost always immediately
        // discarded. Instead, only the native output buffer index of the latest in-window frame
        // is held (never converted) until it is known to be needed: converted immediately if a
        // >=target frame subsequently makes it redundant (then discarded unconverted), or
        // converted once, right before returning, if EOS proves it was the real answer after all.
        var pendingIndex = -1
        fun releasePending() { if (pendingIndex >= 0) { native.releaseOutputBuffer(pendingIndex, false); pendingIndex = -1 } }
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
                    if (bufferInfo.size > 0) {
                        lastObservedPtsUs = bufferInfo.presentationTimeUs; DecodeProfiling.intermediateFrames++
                        if (bufferInfo.presentationTimeUs >= timestampMs * 1000) {
                            releasePending() // strictly superseded; never needed, never converted
                            val image = native.getOutputImage(output) ?: throw MediaFailure("decoder_yuv_unavailable")
                            val convertStart = System.nanoTime()
                            val bitmap = try { convert(image, edge) } finally { image.close(); native.releaseOutputBuffer(output, false) }
                            DecodeProfiling.convertNs += System.nanoTime() - convertStart
                            outputEnded = eof
                            return bitmap
                        } else if (bufferInfo.presentationTimeUs >= timestampMs * 1000 - 100_000) {
                            releasePending()
                            pendingIndex = output
                        } else {
                            native.releaseOutputBuffer(output, false)
                        }
                    } else {
                        native.releaseOutputBuffer(output, false)
                    }
                    outputEnded = eof
                }
            }
            if (!outputEnded) throw MediaFailure("video_decode_timeout")
            if (pendingIndex < 0) return null
            val image = native.getOutputImage(pendingIndex) ?: throw MediaFailure("decoder_yuv_unavailable")
            val convertStart = System.nanoTime()
            val bitmap = try { convert(image, edge) } finally { image.close(); native.releaseOutputBuffer(pendingIndex, false); pendingIndex = -1 }
            DecodeProfiling.convertNs += System.nanoTime() - convertStart
            return bitmap
        } finally { releasePending() }
    }

    private fun convert(image: Image, edge: Int): Bitmap {
        val planes = image.planes
        if (image.format != ImageFormat.YUV_420_888 || planes.size != 3) throw MediaFailure("unsupported_decoder_pixel_format")
        val crop = image.cropRect; val longest = maxOf(crop.width(), crop.height())
        val w = maxOf(1, crop.width() * minOf(edge, longest) / longest)
        val h = maxOf(1, crop.height() * minOf(edge, longest) / longest)
        val pixels = IntArray(w * h)
        // One bulk read per plane instead of 2-3 bounds-checked ByteBuffer.get(index) calls per
        // output pixel (each output pixel reads all three planes): direct-buffer element access
        // still pays a per-call dispatch cost through java.nio.Buffer on this runtime, which a
        // single bulk get(byte[]) into a plain array amortises across the whole plane at once.
        // Copies exactly the plane's own remaining() span (already the codec's stride-correct
        // byte range for this frame); indexing arithmetic afterwards is unchanged.
        val bytes = Array(3) { i -> val b = planes[i].buffer; ByteArray(b.remaining()).also { b.duplicate().get(it) } }
        fun channel(index: Int, x: Int, y: Int): Int = bytes[index][
            y * planes[index].rowStride + x * planes[index].pixelStride].toInt() and 255
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
