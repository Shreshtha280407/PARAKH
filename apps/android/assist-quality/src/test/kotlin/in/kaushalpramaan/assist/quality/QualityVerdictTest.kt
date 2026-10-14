package `in`.kaushalpramaan.assist.quality
import org.junit.Assert.*
import org.junit.Test

class QualityVerdictTest {
    private val thresholds = QualityThresholds("fixture-only", "fixture-only", true, 60.0, 230.0, 0.5, 400.0, 2.0, videoBlurVariance = 100.0)

    private fun sample(t: QualityThresholds, time: Long, mean: Double = 120.0, variance: Double? = 500.0, motion: MotionMetrics? = null): QualitySample {
        val metrics = ImageMetrics(320, 240, mean, 0.0, 0.0, variance)
        return QualitySample(time, metrics, motion, t.flags(metrics, motion, video = true), null, 0.0, 0.0)
    }
    private fun motion(translationPx: Double, reliable: Boolean = true) =
        MotionMetrics(0.0, translationPx.toInt(), 0, translationPx, 1.0, 9, 0.0, reliable)

    @Test fun clearMissingTargetAndOrdinaryLocalMotionDoNotBecomeBad() {
        val samples = listOf(sample(thresholds, 0), sample(thresholds, 125, motion = motion(0.0)), sample(thresholds, 1000))
        assertEquals(false, QualityVerdict.evaluate(samples, 1001, thresholds))
    }

    @Test fun burstPartnerFlagsAndActualCameraMotionCountByDefault() {
        // Default thresholds (no aggregation block parsed) reproduce v1/v2: motion still gates the verdict.
        val samples = listOf(sample(thresholds, 0), sample(thresholds, 125, motion = motion(3.0)))
        assertEquals(true, QualityVerdict.evaluate(samples, 1000, thresholds))
    }

    @Test fun scatteredCameraMotionBlipsOnAnOtherwiseCleanClipAreExcludedFromTheVerdict() {
        // Real evidence from the proxy dataset (e.g. m-5dba026ae2fe): two non-adjacent
        // camera-motion anchors on a video independently reviewed as technically good.
        val gating = thresholds.copy(clipBadFraction = 0.2, cameraMotionCountsTowardBadCapture = true)
        val base = (0 until 10).map { sample(gating, it * 1000L) }.toMutableList()
        base[6] = sample(gating, 6000, motion = motion(3.0))
        base[9] = sample(gating, 9000, motion = motion(3.0))
        assertEquals(true, QualityVerdict.evaluate(base, 10000, gating))
        val excluded = gating.copy(cameraMotionCountsTowardBadCapture = false)
        assertEquals(false, QualityVerdict.evaluate(base, 10000, excluded))
    }

    @Test fun darkMinConsecutiveAnchorsSuppressesFluctuationButNotASustainedRun() {
        val tuned = thresholds.copy(clipBadFraction = 0.3, darkMinConsecutiveAnchors = 4, blurryMinConsecutiveAnchors = 1,
            cameraMotionCountsTowardBadCapture = false)
        // Borderline-dim fluctuation, run length 3 each side: must NOT cross a min-run of 4.
        val fluctuating = listOf(0L, 1000L, 2000L, 3000L, 4000L, 5000L, 6000L, 7000L, 8000L, 9000L, 10000L).map { t ->
            val dim = t in setOf(0L, 1000L, 2000L, 6000L, 7000L, 8000L)
            sample(tuned, t, mean = if (dim) 55.0 else 75.0)
        }
        assertEquals(false, QualityVerdict.evaluate(fluctuating, 11000, tuned))
        // A genuinely sustained dark clip (run length 12) must still cross the same policy.
        val sustained = (0 until 12).map { sample(tuned, it * 1000L, mean = 30.0) }
        assertEquals(true, QualityVerdict.evaluate(sustained, 12000, tuned))
    }

    @Test fun excludedConditionNeverGatesButStillAppearsInItsOwnFlags() {
        val motionExcluded = thresholds.copy(cameraMotionCountsTowardBadCapture = false)
        val samples = listOf(sample(motionExcluded, 0), sample(motionExcluded, 125, motion = motion(3.0)))
        assertEquals(false, QualityVerdict.evaluate(samples, 1000, motionExcluded))
        assertEquals(QualityCondition.CAMERA_MOTION, samples[1].flags.single().condition)
    }

    @Test fun uncalibratedOrAllFailedNeverProducesAVerdict() {
        val uncalibrated = thresholds.copy(calibrated = false)
        assertNull(QualityVerdict.evaluate(listOf(sample(uncalibrated, 0)), 1000, uncalibrated))
        val allFailed = listOf(QualitySample(0, null, null, emptyList(), "video_frame_decode_failed", 0.0, 0.0))
        assertNull(QualityVerdict.evaluate(allFailed, 1000, thresholds))
    }

    @Test fun photoPathIgnoresDurationAndUsesSingleSampleFlags() {
        assertEquals(false, QualityVerdict.evaluate(listOf(sample(thresholds, 0)), null, thresholds))
        assertEquals(true, QualityVerdict.evaluate(listOf(sample(thresholds, 0, mean = 30.0)), null, thresholds))
    }
}
