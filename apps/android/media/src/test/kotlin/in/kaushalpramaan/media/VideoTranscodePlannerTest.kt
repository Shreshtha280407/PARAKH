package `in`.kaushalpramaan.media

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class VideoTranscodePlannerTest {

    @Test
    fun hd_source_with_a_generous_target_keeps_hd_resolution_and_only_trims_bitrate() {
        // 10s HD clip, real bitrate ~8 Mbps (10 MB), target comfortably above the HD floor.
        val source = SourceVideoInfo(durationMs = 10_000, widthPx = 1280, heightPx = 720, bytes = 10_000_000L)
        val plan = VideoTranscodePlanner.plan(source, targetBytes = 6_000_000L)

        check(plan is TranscodePlan.Plan)
        assertEquals("bitrate is reduced before resolution", VideoResolutionProfile.HD, plan.resolution)
        assertTrue(plan.videoBitrateBps >= VideoTranscodePlanner.MIN_VIDEO_BITRATE_BPS_HD)
        assertEquals(VideoTranscodePlanner.AUDIO_BITRATE_BPS, plan.audioBitrateBps)
    }

    @Test
    fun hd_source_with_a_tight_target_steps_down_to_sd_only_once_bitrate_alone_is_insufficient() {
        // Same 10s HD clip, but a target so tight that HD's own bitrate floor cannot be met --
        // resolution must step down to SD, not be attempted at HD below its floor.
        val source = SourceVideoInfo(durationMs = 10_000, widthPx = 1280, heightPx = 720, bytes = 10_000_000L)
        val plan = VideoTranscodePlanner.plan(source, targetBytes = 2_000_000L)

        check(plan is TranscodePlan.Plan)
        assertEquals("lower resolution must only be used once bitrate reduction alone is insufficient", VideoResolutionProfile.SD, plan.resolution)
        assertTrue(plan.videoBitrateBps >= VideoTranscodePlanner.MIN_VIDEO_BITRATE_BPS_SD)
    }

    @Test
    fun sd_source_never_upscales_and_only_ever_reduces_bitrate() {
        val source = SourceVideoInfo(durationMs = 10_000, widthPx = 854, heightPx = 480, bytes = 6_000_000L)
        val plan = VideoTranscodePlanner.plan(source, targetBytes = 3_000_000L)
        check(plan is TranscodePlan.Plan)
        assertEquals(VideoResolutionProfile.SD, plan.resolution)
    }

    @Test
    fun planned_bitrate_times_duration_respects_the_target_budget_with_safety_margin() {
        val source = SourceVideoInfo(durationMs = 20_000, widthPx = 1280, heightPx = 720, bytes = 20_000_000L)
        val target = 5_000_000L
        val plan = VideoTranscodePlanner.plan(source, target)
        check(plan is TranscodePlan.Plan)

        val estimatedOutputBytes = ((plan.videoBitrateBps + plan.audioBitrateBps) * (source.durationMs / 1000.0) / 8.0).toLong()
        assertTrue(
            "planned bitrate ($estimatedOutputBytes bytes estimated) must respect the target ($target) with margin",
            estimatedOutputBytes <= target,
        )
    }

    @Test
    fun impossible_target_reports_CannotFit_with_a_real_floor_estimate_not_zero() {
        val source = SourceVideoInfo(durationMs = 30_000, widthPx = 1280, heightPx = 720, bytes = 30_000_000L)
        val plan = VideoTranscodePlanner.plan(source, targetBytes = 10_000L) // absurdly tiny
        check(plan is TranscodePlan.CannotFit)
        assertTrue(plan.estimatedFloorBytes > 0L)
    }

    @Test
    fun fitting_source_is_not_this_planners_concern_the_caller_checks_that_first() {
        // The planner is only ever invoked once the caller (BudgetLedger.fitDecision) has
        // already decided optimisation is needed -- this just documents that plan() always
        // returns a real plan or CannotFit, never a third "already fits" case, by construction.
        val source = SourceVideoInfo(durationMs = 5_000, widthPx = 1280, heightPx = 720, bytes = 1_000_000L)
        val plan = VideoTranscodePlanner.plan(source, targetBytes = 50_000_000L)
        assertTrue(plan is TranscodePlan.Plan)
    }

    @Test
    fun bitrateBps_is_computed_from_real_bytes_and_duration() {
        val source = SourceVideoInfo(durationMs = 2_000, widthPx = 1280, heightPx = 720, bytes = 1_000_000L)
        assertEquals(4_000_000L, source.bitrateBps) // 1,000,000 bytes * 8 / 2s = 4,000,000 bps
    }
}
