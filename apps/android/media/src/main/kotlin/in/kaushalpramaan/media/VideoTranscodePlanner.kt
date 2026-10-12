package `in`.kaushalpramaan.media

/** Pure, Android-independent description of a captured video's real container metadata --
 * deliberately holds nothing but plain numbers so [VideoTranscodePlanner] is testable without
 * Robolectric or a device. */
data class SourceVideoInfo(val durationMs: Long, val widthPx: Int, val heightPx: Int, val bytes: Long) {
    init {
        require(durationMs > 0) { "durationMs must be positive" }
    }

    val bitrateBps: Long get() = (bytes * 8_000L) / durationMs
}

/** The only two output profiles P5 ever produces -- both SD/HD-compatible H.264/AAC,
 * documented, low-RAM-device-friendly targets (never an arbitrary resolution chosen per
 * clip). */
enum class VideoResolutionProfile(val targetWidth: Int, val targetHeight: Int) {
    HD(1280, 720),
    SD(854, 480),
}

sealed class TranscodePlan {
    /** One planned optimisation pass: the resolution tier and bitrate to encode at. */
    data class Plan(val resolution: VideoResolutionProfile, val videoBitrateBps: Int, val audioBitrateBps: Int) : TranscodePlan()

    /** Even the SD quality floor cannot fit [VideoTranscodePlanner.plan]'s target. */
    data class CannotFit(val estimatedFloorBytes: Long) : TranscodePlan()
}

/**
 * Pure bitrate/resolution planner (P5 spec part D). Given a captured video's real metadata
 * and the exact byte budget it must fit, decides ONE planned optimisation pass: reduce
 * bitrate first, and only step resolution down from HD to SD when bitrate reduction alone
 * at the source's own resolution tier would fall below that tier's documented quality floor.
 * Never touched by Media3/Android types -- [VideoOptimizer] is the one place this plan is
 * actually executed against a real file.
 */
object VideoTranscodePlanner {
    /** Fixed AAC audio bitrate for every P5 output -- not part of the optimisation search
     * space; only video bitrate and resolution are varied. */
    const val AUDIO_BITRATE_BPS = 128_000

    /** Minimum video bitrate below which 720p output stops being a meaningful trade (the
     * point where stepping down to SD instead gives better perceived quality for the same
     * bytes). */
    const val MIN_VIDEO_BITRATE_BPS_HD = 1_200_000

    /** The absolute quality floor: below this even at SD resolution, output is no longer
     * considered usable evidence, and this module refuses to produce a smaller one. */
    const val MIN_VIDEO_BITRATE_BPS_SD = 600_000

    /** Mux/container overhead and, much more significantly, real hardware encoder
     * bitrate-targeting imprecision are real and unavoidable -- measured directly on a real
     * OnePlus 13R (see docs/gates/P5.md): even with `BITRATE_MODE_CBR` explicitly requested
     * (see [in.kaushalpramaan.media.VideoOptimizer]), the actual encoded output landed at
     * roughly 1.3-1.4x the requested bitrate for a short clip, and as much as ~2.3x without
     * CBR mode. This factor is applied to the byte budget before computing a target bitrate
     * so the one planned pass has real headroom against that overshoot -- the same
     * documented-guard-band principle P4's video capture ceiling uses for the same underlying
     * reason (a live/real encoder cannot be told to hit an exact byte count). This does not
     * make the one-pass budget a hard guarantee on every device -- [VideoOptimizer.optimize]
     * still verifies the real output size afterward and reports
     * [VideoOptimizationResult.QualityFloorExceeded] rather than ever adopting an over-budget
     * result. */
    const val CONTAINER_OVERHEAD_SAFETY_FACTOR = 0.6

    fun plan(source: SourceVideoInfo, targetBytes: Long): TranscodePlan {
        val durationSeconds = source.durationMs / 1000.0
        val totalBudgetBps = (targetBytes * 8.0 * CONTAINER_OVERHEAD_SAFETY_FACTOR / durationSeconds).toLong()
        val videoBudgetBps = (totalBudgetBps - AUDIO_BITRATE_BPS).coerceAtLeast(0L)

        val sourceIsHd = source.widthPx >= VideoResolutionProfile.HD.targetWidth || source.heightPx >= VideoResolutionProfile.HD.targetHeight
        val nativeTier = if (sourceIsHd) VideoResolutionProfile.HD else VideoResolutionProfile.SD
        val nativeFloor = if (sourceIsHd) MIN_VIDEO_BITRATE_BPS_HD else MIN_VIDEO_BITRATE_BPS_SD

        // Bitrate-first: the source's own resolution tier (never upscaled past HD) at the
        // computed budget bitrate, as long as that budget does not fall below that tier's
        // quality floor.
        if (videoBudgetBps >= nativeFloor) {
            return TranscodePlan.Plan(nativeTier, videoBudgetBps.toInt(), AUDIO_BITRATE_BPS)
        }

        // Bitrate reduction alone at the native tier would cross below its floor -- only now
        // step resolution down (HD source only; an SD source has nowhere lower to go in this
        // two-tier profile set).
        if (sourceIsHd && videoBudgetBps >= MIN_VIDEO_BITRATE_BPS_SD) {
            return TranscodePlan.Plan(VideoResolutionProfile.SD, videoBudgetBps.toInt(), AUDIO_BITRATE_BPS)
        }

        // Cannot fit even at SD / the quality floor.
        val floorTotalBps = MIN_VIDEO_BITRATE_BPS_SD + AUDIO_BITRATE_BPS
        val estimatedBytes = (floorTotalBps * durationSeconds / 8.0 / CONTAINER_OVERHEAD_SAFETY_FACTOR).toLong()
        return TranscodePlan.CannotFit(estimatedBytes)
    }
}
