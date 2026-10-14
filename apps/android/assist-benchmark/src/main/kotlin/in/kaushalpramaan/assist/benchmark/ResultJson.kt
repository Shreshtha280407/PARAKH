package `in`.kaushalpramaan.assist.benchmark

import `in`.kaushalpramaan.assist.quality.*
import `in`.kaushalpramaan.assist.hands.*
import org.json.JSONArray
import org.json.JSONObject

internal fun obj(vararg values: Pair<String, Any?>) = JSONObject().apply {
    for ((key, value) in values) put(key, value ?: JSONObject.NULL)
}
internal fun ranges(ranges: List<TimeRange>) = JSONArray(ranges.map { obj("start_ms" to it.startMs, "end_ms" to it.endMs) })
internal fun metrics(m: ImageMetrics?) = m?.let { obj("width" to it.width, "height" to it.height,
    "mean_luma" to it.meanLuma, "dark_clip_fraction" to it.darkClipFraction,
    "highlight_clip_fraction" to it.highlightClipFraction, "laplacian_variance" to it.laplacianVariance) }
internal fun motion(m: MotionMetrics?) = m?.let { obj("mean_absolute_difference" to it.meanAbsoluteDifference,
    "shift_x_px" to it.shiftXPx, "shift_y_px" to it.shiftYPx, "translation_px" to it.translationPx,
    "tile_consensus" to it.tileConsensus, "textured_tiles" to it.texturedTiles, "residual_luma" to it.residualLuma, "reliable" to it.reliable) }
internal fun qualityJson(r: QualityResult) = obj("module" to "quality", "status" to r.status.name,
    "module_version" to r.moduleVersion, "threshold_version" to r.thresholdVersion,
    "threshold_sha256" to r.thresholdSha256, "threshold_calibrated" to r.thresholdCalibrated,
    "duration_ms" to r.durationMs, "wall_time_ms" to r.wallTimeMs, "error" to r.error,
    "requested_samples" to r.requestedSampleCount, "analysed_samples" to r.analysedSampleCount,
    "covered_duration_ms" to r.analysedDurationMs,
    "motion_analysed_pairs" to r.motionAnalysedPairCount, "motion_requested_pairs" to r.motionRequestedPairCount,
    "samples" to JSONArray(r.samples.map { s -> obj("timestamp_ms" to s.timestampMs, "metrics" to metrics(s.metrics),
        "motion" to motion(s.motion), "error" to s.error, "decode_ms" to s.decodeMs, "calculation_ms" to s.calculationMs,
        "flags" to JSONArray(s.flags.map { f -> obj("condition" to f.condition.name, "severity" to f.severity,
            "observed" to f.observed, "threshold" to f.threshold) })) }),
    "intervals" to JSONObject().apply { for ((kind, value) in r.intervals) put(kind.name, ranges(value)) })
internal fun handsJson(r: HandsResult) = obj("module" to "hands", "status" to r.status.name,
    "module_version" to r.moduleVersion, "model_version" to r.modelVersion, "model_sha256" to r.modelSha256,
    "configuration_sha256" to r.configurationSha256,
    "delegate" to r.delegate, "sample_interval_ms" to r.sampleIntervalMs, "duration_ms" to r.durationMs,
    "initialization_ms" to r.initializationMs, "wall_time_ms" to r.wallTimeMs, "error" to r.error,
    "visible_ratio" to r.summary.visibleRatio, "analysed_samples" to r.summary.analysedCount,
    "failed_samples" to r.summary.failedCount, "unjudgeable_samples" to r.summary.unjudgeableCount,
    "coverage_fraction" to r.summary.coverageFraction, "covered_duration_ms" to r.summary.coveredDurationMs,
    "hands_not_visible_intervals" to ranges(r.summary.handsNotVisibleIntervals),
    "samples" to JSONArray(r.samples.map { obj("timestamp_ms" to it.timestampMs, "state" to it.state.name,
        "width" to it.widthPx, "height" to it.heightPx,
        "hand_present" to it.handPresent, "hand_count" to it.handCount, "decode_ms" to it.decodeMs,
        "preprocessing_ms" to it.preprocessingMs, "inference_ms" to it.inferenceMs, "error" to it.error,
        "hand_confidences" to JSONArray(it.handConfidences)) }))
