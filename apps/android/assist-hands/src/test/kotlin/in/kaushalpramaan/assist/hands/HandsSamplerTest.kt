package `in`.kaushalpramaan.assist.hands

import `in`.kaushalpramaan.assist.quality.TimeRange
import org.junit.Assert.*
import org.junit.Test

class HandsSamplerTest {
    private fun sample(t: Long, count: Int?, state: HandSampleState = HandSampleState.ANALYSED) =
        HandSample(t, state, count, 0.0, 0.0, 0.0, null)
    @Test fun failedAndUnjudgeableSamplesAreNotNoHands() {
        val result = HandAggregation.summarise(listOf(sample(0, 1), sample(1000, null, HandSampleState.DECODE_FAILED),
            sample(2000, 0), sample(3000, null, HandSampleState.UNJUDGEABLE), sample(4000, 0)), 4500, 1000)
        assertEquals(1.0 / 3, result.visibleRatio!!, 1e-12)
        assertEquals(3, result.analysedCount); assertEquals(1, result.failedCount); assertEquals(1, result.unjudgeableCount)
        assertEquals(0.6, result.coverageFraction, 1e-12)
        assertEquals(listOf(TimeRange(2000, 3000), TimeRange(4000, 4500)), result.handsNotVisibleIntervals)
    }
    @Test fun noAnalysableSamplesHaveNullRatio() {
        val result = HandAggregation.summarise(listOf(sample(0, null, HandSampleState.INFERENCE_FAILED)), 1000, 1000)
        assertNull(result.visibleRatio); assertTrue(result.handsNotVisibleIntervals.isEmpty())
    }
    @Test fun unorderedInferenceTimesAreRejected() {
        assertThrows(IllegalArgumentException::class.java) {
            HandAggregation.summarise(listOf(sample(1000, 0), sample(0, 1)), 2000, 1000)
        }
    }
    @Test fun handConfidencesAreOptionalButMustMatchDetectedCountWhenPresent() {
        HandSample(0, HandSampleState.ANALYSED, 2, 0.0, 0.0, 0.0, null, handConfidences = listOf(0.9, 0.6))
        HandSample(0, HandSampleState.ANALYSED, 1, 0.0, 0.0, 0.0, null) // empty confidences always allowed
        assertThrows(IllegalArgumentException::class.java) {
            HandSample(0, HandSampleState.ANALYSED, 2, 0.0, 0.0, 0.0, null, handConfidences = listOf(0.9))
        }
        assertThrows(IllegalArgumentException::class.java) {
            HandSample(0, HandSampleState.ANALYSED, 1, 0.0, 0.0, 0.0, null, handConfidences = listOf(1.5))
        }
    }
    @Test fun isolatedSingleSampleMissBracketedByDetectionsIsGapFilled() {
        // Real evidence from the proxy dataset: a lone ANALYSED/no-hand sample between two
        // ANALYSED/present samples is far more often a momentary miss than a true 1s absence.
        val result = HandAggregation.summarise(listOf(sample(0, 1), sample(1000, 0), sample(2000, 1)), 3000, 1000)
        assertEquals(2.0 / 3, result.visibleRatio!!, 1e-12) // raw field is completely unchanged
        assertEquals(listOf(TimeRange(1000, 2000)), result.handsNotVisibleIntervals)
        assertEquals(1.0, result.visibleRatioGapFilled!!, 1e-12) // gap-filled view fills the isolated miss
        assertTrue(result.handsNotVisibleIntervalsGapFilled.isEmpty())
    }
    @Test fun sustainedTwoSampleMissIsNotGapFilled() {
        // A gap of 2+ consecutive misses is a real absence, not noise; k=1 must not fill it.
        val result = HandAggregation.summarise(listOf(sample(0, 1), sample(1000, 0), sample(2000, 0), sample(3000, 1)), 4000, 1000)
        assertEquals(listOf(TimeRange(1000, 3000)), result.handsNotVisibleIntervalsGapFilled)
    }
    @Test fun gapFillNeverFillsAcrossAFailedOrUnjudgeableNeighbour() {
        // A failed/unjudgeable sample must never become evidence for filling an adjacent miss:
        // this reinterprets existing detections, it must never invent one from a missing value.
        val result = HandAggregation.summarise(listOf(sample(0, 1), sample(1000, null, HandSampleState.DECODE_FAILED),
            sample(2000, 0), sample(3000, 1)), 4000, 1000)
        assertEquals(listOf(TimeRange(2000, 3000)), result.handsNotVisibleIntervalsGapFilled)
    }
    @Test fun gapFillNeverFillsAtAClipBoundaryWithNoNeighbourOnOneSide() {
        val result = HandAggregation.summarise(listOf(sample(0, 0), sample(1000, 1)), 2000, 1000)
        assertEquals(listOf(TimeRange(0, 1000)), result.handsNotVisibleIntervalsGapFilled)
    }
    @Test fun noAnalysableSamplesHaveNullGapFilledRatioToo() {
        val result = HandAggregation.summarise(listOf(sample(0, null, HandSampleState.INFERENCE_FAILED)), 1000, 1000)
        assertNull(result.visibleRatioGapFilled)
    }
}
