package `in`.kaushalpramaan.assist.quality
import org.junit.Assert.*
import org.junit.Test

class QualityThresholdTest {
    private val thresholds = QualityThresholds("fixture-only", "fixture-only", true, 60.0, 230.0, 0.5, 40.0, 2.0)
    private fun metrics(mean: Double, variance: Double? = 100.0, clipped: Double = 0.0) =
        ImageMetrics(320, 180, mean, 0.0, clipped, variance)
    @Test fun darkDoesNotInventDefocusAndClippingUsesBothRules() {
        assertEquals(listOf(QualityCondition.DARK), thresholds.flags(metrics(59.9, 0.0)).map { it.condition })
        assertTrue(thresholds.flags(metrics(230.0, 100.0, 1.0)).isEmpty())
        assertTrue(thresholds.flags(metrics(240.0, 100.0, 0.5)).isEmpty())
        assertEquals(listOf(QualityCondition.OVEREXPOSED), thresholds.flags(metrics(240.0, 100.0, 0.6)).map { it.condition })
    }
    @Test fun blurAndMotionRespectBoundaryReliabilityAndObservedUnits() {
        assertEquals(listOf(QualityCondition.BLURRY), thresholds.flags(metrics(120.0, 39.9)).map { it.condition })
        assertTrue(thresholds.flags(metrics(120.0, 40.0)).isEmpty())
        assertTrue(thresholds.flags(metrics(120.0, null)).isEmpty())
        val motion = MotionMetrics(100.0, 2, 0, 2.0, 1.0, 9, 0.0, true)
        val flag = thresholds.flags(metrics(120.0), motion).single()
        assertEquals(QualityCondition.CAMERA_MOTION, flag.condition); assertEquals(2.0, flag.observed, 0.0)
        assertEquals("review", flag.severity)
        assertTrue(thresholds.flags(metrics(120.0), motion.copy(reliable = false)).isEmpty())
    }
    @Test fun videoCompressionUsesItsOwnCalibratedBlurBoundary() {
        val profile = thresholds.copy(blurVariance = 400.0, videoBlurVariance = 40.0)
        assertTrue(profile.flags(metrics(120.0, 100.0)).any { it.condition == QualityCondition.BLURRY })
        assertFalse(profile.flags(metrics(120.0, 100.0), video = true).any { it.condition == QualityCondition.BLURRY })
        assertEquals(40.0, profile.flags(metrics(120.0, 39.0), video = true).single().threshold, 0.0)
    }
}
