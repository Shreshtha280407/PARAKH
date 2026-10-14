package `in`.kaushalpramaan.assist.quality

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.sqrt

/** Row-major, unsigned 8-bit gamma-encoded luma; no image or evidence mutation. */
data class GrayFrame(val width: Int, val height: Int, val pixels: ByteArray) {
    init { require(width > 0 && height > 0 && width.toLong() * height == pixels.size.toLong()) }
    fun at(x: Int, y: Int): Int = pixels[y * width + x].toInt() and 255
}

data class ImageMetrics(val width: Int, val height: Int, val meanLuma: Double,
    val darkClipFraction: Double, val highlightClipFraction: Double, val laplacianVariance: Double?)

object QualityMetrics {
    const val DEFINITION_VERSION = "luma77-150-29-laplacian4-interior-population-v1"
    /** Integer BT.601 approximation, gamma-encoded RGB, rounded by +128 then >>8. */
    fun luma(argb: Int): Int = (77 * ((argb ushr 16) and 255) +
        150 * ((argb ushr 8) and 255) + 29 * (argb and 255) + 128) ushr 8

    fun calculate(frame: GrayFrame, darkClip: Int = 16, highlightClip: Int = 235): ImageMetrics {
        require(darkClip in 0..254 && highlightClip in (darkClip + 1)..255)
        var sum = 0L; var dark = 0; var light = 0
        for (byte in frame.pixels) {
            val value = byte.toInt() and 255
            sum += value; if (value <= darkClip) dark++; if (value >= highlightClip) light++
        }
        var count = 0; var mean = 0.0; var m2 = 0.0
        for (y in 1 until frame.height - 1) for (x in 1 until frame.width - 1) {
            val lap = frame.at(x - 1, y) + frame.at(x + 1, y) + frame.at(x, y - 1) +
                frame.at(x, y + 1) - 4 * frame.at(x, y)
            count++
            val delta = lap - mean
            mean += delta / count
            m2 += delta * (lap - mean)
        }
        val n = frame.pixels.size.toDouble()
        return ImageMetrics(frame.width, frame.height, sum / n, dark / n, light / n,
            if (count > 0) max(0.0, m2 / count) else null)
    }

    /** Box mean over non-overlapping 4x4 blocks; incomplete right/bottom blocks omitted. */
    fun motionFrame(frame: GrayFrame): GrayFrame? {
        val w = frame.width / 4; val h = frame.height / 4
        if (w < 24 || h < 24) return null
        val out = ByteArray(w * h)
        for (y in 0 until h) for (x in 0 until w) {
            var sum = 0
            for (dy in 0..3) for (dx in 0..3) sum += frame.at(x * 4 + dx, y * 4 + dy)
            out[y * w + x] = ((sum + 8) / 16).toByte()
        }
        return GrayFrame(w, h, out)
    }
}

data class MotionMetrics(val meanAbsoluteDifference: Double, val shiftXPx: Int, val shiftYPx: Int,
    val translationPx: Double, val tileConsensus: Double, val texturedTiles: Int,
    val residualLuma: Double, val reliable: Boolean)

/** Translation-only camera-motion proxy, on ~80px gray. Local motion is not called shake.
 * Nine 12x12 tiles independently search +/-4px with brightness-centred mean absolute error.
 * A majority must agree on a nonzero shift. Rotation, rolling shutter, large displacement,
 * low texture and occlusion limit this observable; reliable=false is not proof of stability.
 */
object CameraMotion {
    const val DEFINITION_VERSION = "tile9-centered-mad-translation-radius4-patch12-neighbour1-v2"
    private val shifts = (-4..4).flatMap { dy -> (-4..4).map { dx -> dx to dy } }
        .sortedWith(compareBy<Pair<Int, Int>> { it.first * it.first + it.second * it.second }
            .thenBy { it.second }.thenBy { it.first })
    fun measure(previous: GrayFrame, current: GrayFrame): MotionMetrics? {
        if (previous.width != current.width || previous.height != current.height ||
            previous.width < 24 || previous.height < 24) return null
        val w = previous.width; val h = previous.height
        var rawDifference = 0.0
        for (i in previous.pixels.indices) rawDifference += abs((previous.pixels[i].toInt() and 255) -
            (current.pixels[i].toInt() and 255))
        val votes = mutableListOf<Triple<Int, Int, Double>>()
        for (gy in 0..2) for (gx in 0..2) {
            val left = ((2 * gx + 1) * w / 6 - 6).coerceIn(4, w - 16)
            val top = ((2 * gy + 1) * h / 6 - 6).coerceIn(4, h - 16)
            var refMean = 0.0; var refSquared = 0.0
            for (y in 0..11) for (x in 0..11) {
                val value = previous.at(left + x, top + y).toDouble()
                refMean += value; refSquared += value * value
            }
            refMean /= 144
            if (refSquared / 144 - refMean * refMean < 25) continue
            var best = Double.POSITIVE_INFINITY; var bestX = 0; var bestY = 0
            // Prefer zero/smaller translation on ties, not the first corner of the search window.
            for ((dx, dy) in shifts) {
                var targetMean = 0.0
                for (y in 0..11) for (x in 0..11) targetMean += current.at(left + x + dx, top + y + dy)
                targetMean /= 144
                var cost = 0.0
                for (y in 0..11) for (x in 0..11) cost += abs(previous.at(left + x, top + y) - refMean -
                    current.at(left + x + dx, top + y + dy) + targetMean)
                cost /= 144
                if (cost < best - 1e-9) { best = cost; bestX = dx; bestY = dy }
            }
            votes += Triple(bestX, bestY, best)
        }
        // Integer block matching differs by a pixel with mild perspective/rotation and
        // resampling. Require spatially coherent neighbouring vectors, not exact equality.
        // A moving minority of tiles still cannot override a stable background majority.
        val dominant = votes.map { center -> votes.filter {
            abs(it.first - center.first) <= 1 && abs(it.second - center.second) <= 1
        } }.sortedWith(compareByDescending<List<Triple<Int, Int, Double>>> { it.size }
            .thenBy { cluster -> cluster.sumOf { it.first * it.first + it.second * it.second } }).firstOrNull().orEmpty()
        val dx = dominant.map { it.first }.sorted().let { if (it.isEmpty()) 0 else it[it.size / 2] }
        val dy = dominant.map { it.second }.sorted().let { if (it.isEmpty()) 0 else it[it.size / 2] }
        val consensus = if (votes.isEmpty()) 0.0 else dominant.size.toDouble() / votes.size
        val residual = if (dominant.isEmpty()) 255.0 else dominant.map { it.third }.average()
        return MotionMetrics(rawDifference / previous.pixels.size, dx, dy,
            sqrt((dx * dx + dy * dy).toDouble()), consensus, votes.size, residual,
            votes.size >= 5 && consensus >= 2.0 / 3 && residual <= 20.0)
    }
}

enum class ColorStandard { BT601, BT709, BT2020 }

/**
 * Exact-integer SDR YUV-to-RGB conversion via precomputed per-channel lookup tables.
 * Produces bit-identical output to evaluating the direct per-pixel integer formula this
 * replaces (`yy +/- coefficient*channel`, `shr 8`, clamp), because each table entry IS that
 * exact product precomputed once; only the redundant per-pixel multiplication is removed.
 * One instance is built once per (standard, range) pair — there are only six combinations —
 * and reused across every pixel of every frame of a video, instead of recomputing the four
 * coefficients from scratch on every single frame.
 */
class YuvToRgb(standard: ColorStandard, fullRange: Boolean) {
    private val rv: Int
    private val gu: Int
    private val gv: Int
    private val bu: Int
    init {
        val bt709 = standard == ColorStandard.BT709
        val bt2020 = standard == ColorStandard.BT2020
        rv = if (fullRange) { if (bt709) 403 else if (bt2020) 377 else 359 } else { if (bt709) 459 else if (bt2020) 430 else 409 }
        gu = if (fullRange) { if (bt709) 48 else if (bt2020) 42 else 88 } else { if (bt709) 55 else if (bt2020) 48 else 100 }
        gv = if (fullRange) { if (bt709) 120 else if (bt2020) 146 else 183 } else { if (bt709) 136 else if (bt2020) 167 else 208 }
        bu = if (fullRange) { if (bt709) 475 else if (bt2020) 482 else 454 } else { if (bt709) 541 else if (bt2020) 548 else 516 }
    }
    private val yTable = IntArray(256) { if (fullRange) 256 * it else 298 * (it - 16) }
    private val rvTable = IntArray(256) { rv * (it - 128) }
    private val guTable = IntArray(256) { gu * (it - 128) }
    private val gvTable = IntArray(256) { gv * (it - 128) }
    private val buTable = IntArray(256) { bu * (it - 128) }

    /** Packs one opaque ARGB_8888 pixel from raw 8-bit Y/U/V channel bytes (0..255). */
    fun argb(y: Int, u: Int, v: Int): Int {
        val yy = yTable[y]
        val r = ((yy + rvTable[v] + 128) shr 8).coerceIn(0, 255)
        val g = ((yy - guTable[u] - gvTable[v] + 128) shr 8).coerceIn(0, 255)
        val b = ((yy + buTable[u] + 128) shr 8).coerceIn(0, 255)
        return (255 shl 24) or (r shl 16) or (g shl 8) or b
    }
}

data class TimeRange(val startMs: Long, val endMs: Long) {
    init { require(startMs >= 0 && endMs > startMs) }
}

object SampleTimes {
    const val MAX_DURATION_MS = 20 * 60 * 1000L
    fun regular(durationMs: Long, intervalMs: Long = 1000): List<Long> {
        require(durationMs in 1..MAX_DURATION_MS && intervalMs in 500..1000)
        return generateSequence(0L) { it + intervalMs }.takeWhile { it < durationMs }.toList()
    }
    /** Each quality sample has an optional 125ms partner, exposing motion missed at 1fps. */
    fun quality(durationMs: Long): List<Long> = regular(durationMs).flatMap {
        if (it + 125 < durationMs) listOf(it, it + 125) else listOf(it)
    }
    /** Left-anchored sample cells [t,min(t+step,duration)); failed/unknown samples break runs. */
    fun intervals(samples: List<Pair<Long, Boolean?>>, durationMs: Long, intervalMs: Long): List<TimeRange> {
        require(intervalMs in 1..1000 && durationMs > 0)
        require(samples.zipWithNext().all { it.second.first - it.first.first >= intervalMs })
        require(samples.all { it.first in 0 until durationMs })
        val out = mutableListOf<TimeRange>()
        for ((time, flagged) in samples) if (flagged == true) {
            val end = minOf(durationMs, time + intervalMs)
            if (out.lastOrNull()?.endMs == time) out[out.lastIndex] = TimeRange(out.last().startMs, end)
            else out += TimeRange(time, end)
        }
        return out
    }
}
