package `in`.kaushalpramaan.assist.quality

/**
 * Combined clip-level "review-worthy" hint, derived from the same per-sample flags
 * [QualityAnalyzer] already reports as [TimeRange] intervals. This is an assistance hint,
 * never a probability, competence score, or acceptance/rejection decision, and it never
 * blocks evidence submission.
 *
 * A condition only contributes to the combined verdict once it persists for its own minimum
 * run of consecutive 1s anchors (an isolated single flagged anchor is treated as noise, a
 * sustained run is not). CAMERA_MOTION can be excluded from the verdict entirely while still
 * being computed and exposed via its own [QualityCondition.CAMERA_MOTION] interval, since its
 * own standalone precision is calibrated separately and may be too weak to gate a verdict even
 * though it remains a useful disclosed hint. This mirrors `technical_prediction` in
 * `ml/assistance/protocol.py`; keep both in parity and covered by matching unit tests.
 */
object QualityVerdict {
    fun evaluate(samples: List<QualitySample>, durationMs: Long?, thresholds: QualityThresholds): Boolean? {
        if (!thresholds.calibrated || samples.none { it.metrics != null }) return null
        if (durationMs == null) {
            val sample = samples.firstOrNull() ?: return null
            return sample.metrics?.let { sample.flags.isNotEmpty() }
        }
        val lookup = samples.associateBy { it.timestampMs }
        val anchors = samples.filter { it.timestampMs % 1000 == 0L }
        if (anchors.isEmpty()) return null
        val combined = anchors.associate { anchor ->
            val partner = lookup[anchor.timestampMs + 125]
            val flags = anchor.flags.map { it.condition }.toSet() + (partner?.flags?.map { it.condition }?.toSet() ?: emptySet())
            anchor.timestampMs to flags
        }
        val minRun = mapOf(QualityCondition.DARK to thresholds.darkMinConsecutiveAnchors,
            QualityCondition.BLURRY to thresholds.blurryMinConsecutiveAnchors)
        val excluded = if (thresholds.cameraMotionCountsTowardBadCapture) emptySet() else setOf(QualityCondition.CAMERA_MOTION)
        val observedConditions = combined.values.flatten().toSet()
        val qualifying = mutableSetOf<Long>()
        for (condition in observedConditions - excluded) {
            val required = minRun[condition] ?: 1
            var run = mutableListOf<Long>()
            for (anchor in anchors) {
                val time = anchor.timestampMs
                if (condition in combined.getValue(time)) run.add(time)
                else { if (run.size >= required) qualifying += run; run = mutableListOf() }
            }
            if (run.size >= required) qualifying += run
        }
        return qualifying.size.toDouble() / anchors.size >= thresholds.clipBadFraction
    }
}
