package `in`.kaushalpramaan.assist.quality

import org.junit.Assert.*
import org.junit.Test

class QualityCoreTest {
    private fun frame(w: Int = 80, h: Int = 60, pixel: (Int, Int) -> Int): GrayFrame =
        GrayFrame(w, h, ByteArray(w * h) { pixel(it % w, it / w).toByte() })
    private fun pattern(x: Int, y: Int): Int { var n = x * 73856093 xor (y * 19349663); n = n xor (n ushr 13); return n and 255 }

    @Test fun lumaUsesDocumentedIntegerWeights() {
        assertEquals(0, QualityMetrics.luma(0xff000000.toInt()))
        assertEquals(255, QualityMetrics.luma(0xffffffff.toInt()))
        assertEquals(77, QualityMetrics.luma(0xffff0000.toInt()))
        assertEquals(149, QualityMetrics.luma(0xff00ff00.toInt()))
        assertEquals(29, QualityMetrics.luma(0xff0000ff.toInt()))
    }
    @Test fun constantImageHasNoLaplacianVarianceAndClippingIsInclusive() {
        val dark = QualityMetrics.calculate(frame { _, _ -> 16 })
        assertEquals(16.0, dark.meanLuma, 0.0); assertEquals(1.0, dark.darkClipFraction, 0.0)
        assertEquals(0.0, dark.laplacianVariance!!, 0.0)
        assertEquals(1.0, QualityMetrics.calculate(frame { _, _ -> 235 }).highlightClipFraction, 0.0)
    }
    @Test fun tinyImagesHaveExplicitlyUnavailableBlur() {
        assertNull(QualityMetrics.calculate(frame(1, 2) { _, _ -> 100 }).laplacianVariance)
        assertNull(QualityMetrics.motionFrame(frame(8, 8) { _, _ -> 10 }))
    }
    @Test fun coherentTranslationIsDetected() {
        val a = frame(pixel = ::pattern)
        val b = frame { x, y -> pattern(x - 2, y + 1) }
        val motion = CameraMotion.measure(a, b)!!
        assertTrue(motion.reliable); assertEquals(2, motion.shiftXPx); assertEquals(-1, motion.shiftYPx)
        assertEquals(1.0, motion.tileConsensus, 0.0)
    }
    @Test fun localObjectMotionDoesNotBecomeGlobalCameraMotion() {
        val a = frame(pixel = ::pattern)
        val b = frame { x, y -> if (x in 34..46 && y in 24..36) pattern(x - 3, y) else pattern(x, y) }
        val motion = CameraMotion.measure(a, b)!!
        assertTrue(motion.reliable); assertEquals(0.0, motion.translationPx, 0.0)
    }
    @Test fun smallSpatialVariationUsesCoherentNeighbouringVotes() {
        val a = frame(pixel = ::pattern)
        val b = frame { x, y -> pattern(x - when { x < 27 -> 1; x < 54 -> 2; else -> 3 }, y) }
        val motion = CameraMotion.measure(a, b)!!
        assertTrue(motion.reliable); assertEquals(2, motion.shiftXPx); assertEquals(0, motion.shiftYPx)
        assertEquals(1.0, motion.tileConsensus, 0.0)
    }
    @Test fun brightnessChangeAndLowTextureAreNotCameraShake() {
        val a = frame { x, y -> pattern(x, y) / 2 }
        val b = frame { x, y -> pattern(x, y) / 2 + 30 }
        assertEquals(0.0, CameraMotion.measure(a, b)!!.translationPx, 0.0)
        assertFalse(CameraMotion.measure(frame { _, _ -> 100 }, frame { _, _ -> 110 })!!.reliable)
    }
    @Test fun samplerIsOrderedBoundedAndIncludesBriefMotionPartners() {
        assertEquals(listOf(0L, 1000L), SampleTimes.regular(1001))
        assertEquals(listOf(0L, 125L, 1000L), SampleTimes.quality(1001))
        assertEquals(listOf(0L), SampleTimes.quality(1))
        assertThrows(IllegalArgumentException::class.java) { SampleTimes.regular(0) }
        assertThrows(IllegalArgumentException::class.java) { SampleTimes.regular(SampleTimes.MAX_DURATION_MS + 1) }
    }
    @Test fun failedSamplesBreakIntervalsAndTailIsClamped() {
        assertEquals(listOf(TimeRange(0, 1000), TimeRange(2000, 2501)), SampleTimes.intervals(
            listOf(0L to true, 1000L to null, 2000L to true), 2501, 1000))
        assertThrows(IllegalArgumentException::class.java) { SampleTimes.intervals(listOf(1L to true, 1L to true), 100, 1000) }
    }
    @Test fun uncalibratedProfileNeverClaimsFlags() {
        val profile = QualityThresholds("test", "test", false, 100.0, 230.0, 0.5, 100.0, 2.0)
        assertTrue(profile.flags(QualityMetrics.calculate(frame { _, _ -> 0 })).isEmpty())
    }
}
