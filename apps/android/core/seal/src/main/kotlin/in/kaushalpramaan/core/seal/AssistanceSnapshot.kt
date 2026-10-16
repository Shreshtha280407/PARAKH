package `in`.kaushalpramaan.core.seal

import kotlinx.serialization.Serializable

@Serializable
enum class AssistanceStatus { NOT_RUN, QUEUED, RUNNING, COMPLETED, PARTIAL, FAILED, UNAVAILABLE }

@Serializable
enum class AssistanceFlagType { DARK, OVEREXPOSED, BLURRY, CAMERA_MOTION, HANDS_NOT_DETECTED }

@Serializable
enum class AssistanceError { CANCELLED, INTERRUPTED, MEDIA_UNAVAILABLE, INPUT_CHANGED, ANALYSIS_FAILED, MODEL_UNAVAILABLE, INCOMPLETE_COVERAGE, PAYLOAD_LIMIT }

@Serializable
data class AssistanceFlag(
    val type: AssistanceFlagType,
    val startMs: Long = 0,
    val endMs: Long? = null,
    val severity: String = "review",
    val observed: Double? = null,
    val threshold: Double? = null,
) {
    init {
        require(startMs in 0..1_200_000 && (endMs == null || endMs > startMs && endMs <= 1_200_000))
        require(severity == "review")
        require(observed == null || observed.isFinite() && observed >= 0)
        require(threshold == null || threshold.isFinite() && threshold >= 0)
    }
}

@Serializable
data class AssistanceProvenance(
    val moduleVersion: String,
    val profileVersion: String,
    val profileSha256: String,
    val modelSha256: String? = null,
    val sampleIntervalMs: Long = 1000,
) {
    init {
        require(moduleVersion.length in 1..80 && profileVersion.length in 1..80)
        require(profileSha256.matches(HASH) && (modelSha256 == null || modelSha256.matches(HASH)))
        require(sampleIntervalMs == 1000L)
    }
}

@Serializable
data class AssistanceCoverage(
    val requestedSamples: Int,
    val analysedSamples: Int,
    val coveredDurationMs: Long,
    val motionRequestedPairs: Int = 0,
    val motionAnalysedPairs: Int = 0,
) {
    init {
        require(requestedSamples in 0..2400 && analysedSamples in 0..requestedSamples)
        require(coveredDurationMs in 0..1_200_000)
        require(motionRequestedPairs in 0..1200 && motionAnalysedPairs in 0..motionRequestedPairs)
    }
}

@Serializable
data class AssistanceAnalysis(
    val status: AssistanceStatus,
    val provenance: AssistanceProvenance?,
    val coverage: AssistanceCoverage,
    val reviewRecommended: Boolean? = null,
    val visibleRatio: Double? = null,
    val visibleRatioGapFilled: Double? = null,
) {
    init {
        require(status in setOf(AssistanceStatus.COMPLETED, AssistanceStatus.PARTIAL, AssistanceStatus.FAILED, AssistanceStatus.UNAVAILABLE))
        require(visibleRatio == null || visibleRatio.isFinite() && visibleRatio in 0.0..1.0)
        require(visibleRatioGapFilled == null || visibleRatioGapFilled.isFinite() && visibleRatioGapFilled in 0.0..1.0)
        if (status in setOf(AssistanceStatus.COMPLETED, AssistanceStatus.PARTIAL)) require(provenance != null && coverage.analysedSamples > 0)
        if (status in setOf(AssistanceStatus.FAILED, AssistanceStatus.UNAVAILABLE)) {
            require(coverage.analysedSamples == 0 && reviewRecommended == null && visibleRatio == null && visibleRatioGapFilled == null)
        }
    }
}

/** Compact client-originated advisory metadata, signed with the evidence. No landmarks,
 * scores, identity claims or arbitrary diagnostic objects. Times are sampled source cells. */
@Serializable
data class AssistanceSnapshot(
    val contractVersion: Int = 1,
    val source: String = "ON_DEVICE",
    val assessmentId: String,
    val taskId: String,
    val evidenceId: String,
    val revisionId: String,
    val revisionNumber: Int,
    val mediaSha256: String,
    val durationMs: Long? = null,
    val status: AssistanceStatus,
    val quality: AssistanceAnalysis? = null,
    val hands: AssistanceAnalysis? = null,
    val flags: List<AssistanceFlag> = emptyList(),
    val completedAtMillis: Long? = null,
    val errorCategory: AssistanceError? = null,
    val intervalsTruncated: Boolean = false,
) {
    init {
        require(contractVersion == 1 && source == "ON_DEVICE")
        require(listOf(assessmentId, evidenceId, revisionId).all { it.length in 1..64 })
        require(taskId in setOf("T1", "T2", "T3", "T4", "T5") && revisionNumber >= 1)
        require(mediaSha256.matches(HASH))
        // The analyzer's 20-minute safety cap is not an evidence submission limit.
        // Longer valid media still carries an honest failed/unavailable snapshot.
        require(durationMs == null || durationMs in 1..9_007_199_254_740_991L)
        require(flags.size <= 256 && (completedAtMillis == null || completedAtMillis in 0..9_007_199_254_740_991L))
        require(flags.distinct() == flags)
        flags.forEach {
            if (durationMs == null) require(it.startMs == 0L && it.endMs == null && it.type != AssistanceFlagType.HANDS_NOT_DETECTED && it.type != AssistanceFlagType.CAMERA_MOTION)
            else require(it.endMs != null && it.startMs < durationMs && it.endMs <= durationMs)
            val analysis = if (it.type == AssistanceFlagType.HANDS_NOT_DETECTED) hands else quality
            require(analysis?.status in setOf(AssistanceStatus.COMPLETED, AssistanceStatus.PARTIAL))
        }
        listOfNotNull(quality, hands).forEach {
            require(it.coverage.coveredDurationMs <= (durationMs ?: 0))
        }
        if (durationMs == null) require(hands == null)
        if (hands != null && hands.status in setOf(AssistanceStatus.COMPLETED, AssistanceStatus.PARTIAL)) require(hands.provenance?.modelSha256 != null)
        if (quality != null) require(quality.visibleRatio == null && quality.visibleRatioGapFilled == null && quality.provenance?.modelSha256 == null)
        if (hands != null) require(hands.reviewRecommended == null)
        if (status in setOf(AssistanceStatus.NOT_RUN, AssistanceStatus.QUEUED, AssistanceStatus.RUNNING)) {
            require(quality == null && hands == null && flags.isEmpty() && completedAtMillis == null)
        }
        if (status == AssistanceStatus.COMPLETED) {
            require(quality?.status == AssistanceStatus.COMPLETED && (durationMs == null || hands?.status == AssistanceStatus.COMPLETED))
        }
        if (status in setOf(AssistanceStatus.COMPLETED, AssistanceStatus.PARTIAL)) require(completedAtMillis != null)
        if (status == AssistanceStatus.PARTIAL) require(listOfNotNull(quality, hands).any { it.status in setOf(AssistanceStatus.COMPLETED, AssistanceStatus.PARTIAL) })
        if (status in setOf(AssistanceStatus.FAILED, AssistanceStatus.UNAVAILABLE)) require(flags.isEmpty() && listOfNotNull(quality, hands).none { it.status in setOf(AssistanceStatus.COMPLETED, AssistanceStatus.PARTIAL) })
        if (intervalsTruncated) require(status == AssistanceStatus.PARTIAL && errorCategory == AssistanceError.PAYLOAD_LIMIT)
    }

    fun validateBinding(assessment: String, task: String, evidence: String, hash: String, duration: Long?) {
        require(assessmentId == assessment && taskId == task && evidenceId == evidence && mediaSha256 == hash && durationMs == duration)
    }
}

private val HASH = Regex("[0-9a-f]{64}")
