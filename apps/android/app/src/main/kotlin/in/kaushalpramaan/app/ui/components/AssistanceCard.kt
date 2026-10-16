package `in`.kaushalpramaan.app.ui.components

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.assistance.AssistanceRecord
import `in`.kaushalpramaan.app.data.assistance.EvidenceAssistanceCoordinator
import `in`.kaushalpramaan.core.seal.*
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import java.util.Locale

@Composable
fun AssistanceCard(record: AssistanceRecord?, sealed: Boolean, compact: Boolean = false,
    onRetry: (() -> Unit)? = null, onCancel: (() -> Unit)? = null) {
    val snapshot = remember(record, sealed) {
        (if (sealed) record?.sealedSnapshotJson else record?.resultJson)?.let {
            runCatching { EvidenceAssistanceCoordinator.JSON.decodeFromString<AssistanceSnapshot>(it) }.getOrNull()
        }
    }
    val state = snapshot?.status ?: record?.status?.let { AssistanceStatus.valueOf(it) } ?: AssistanceStatus.NOT_RUN
    val pending = state in setOf(AssistanceStatus.QUEUED, AssistanceStatus.RUNNING)
    val label = when (state) {
        AssistanceStatus.NOT_RUN -> R.string.assistance_not_run
        AssistanceStatus.QUEUED -> R.string.assistance_queued
        AssistanceStatus.RUNNING -> R.string.assistance_running
        AssistanceStatus.COMPLETED -> R.string.assistance_completed
        AssistanceStatus.PARTIAL -> R.string.assistance_partial
        AssistanceStatus.FAILED -> R.string.assistance_failed
        AssistanceStatus.UNAVAILABLE -> R.string.assistance_unavailable
    }
    Column(Modifier.fillMaxWidth().padding(vertical = 8.dp).testTag("assistance_summary")) {
        Text(stringResource(label), style = MaterialTheme.typography.titleSmall)
        if (pending && !sealed) LinearProgressIndicator(Modifier.fillMaxWidth().padding(vertical = 4.dp))
        if (sealed) Text(stringResource(R.string.assistance_sealed_snapshot), style = MaterialTheme.typography.bodySmall)
        if (pending && !sealed && !compact) Text(stringResource(if (record?.stage == "hands") R.string.assistance_stage_hands else R.string.assistance_stage_quality), style = MaterialTheme.typography.bodySmall)
        if (compact && snapshot?.flags?.isNotEmpty() == true) Text(stringResource(R.string.assistance_warning_count, snapshot.flags.map { it.type }.distinct().size), style = MaterialTheme.typography.bodySmall)
        if (!compact) snapshot?.flags?.groupBy { it.type }?.forEach { (type, flags) ->
            Text(stringResource(when (type) {
                AssistanceFlagType.DARK -> R.string.assistance_dark
                AssistanceFlagType.OVEREXPOSED -> R.string.assistance_overexposed
                AssistanceFlagType.BLURRY -> R.string.assistance_blurry
                AssistanceFlagType.CAMERA_MOTION -> R.string.assistance_motion
                AssistanceFlagType.HANDS_NOT_DETECTED -> R.string.assistance_hands_warning
            }), style = MaterialTheme.typography.bodyMedium)
            if (!compact) flags.take(4).filter { it.endMs != null }.forEach {
                Text("${sourceTime(it.startMs)} – ${sourceTime(it.endMs!!)}", style = MaterialTheme.typography.bodySmall)
            }
        }
        if (!compact) {
            snapshot?.hands?.let { h ->
                Text(stringResource(if (h.status in setOf(AssistanceStatus.FAILED, AssistanceStatus.UNAVAILABLE))
                    R.string.assistance_hands_unavailable else R.string.assistance_hands_sampled), style = MaterialTheme.typography.bodySmall)
            }
            snapshot?.let { result ->
                val valid = listOfNotNull(result.quality, result.hands).sumOf { it.coverage.analysedSamples }
                val requested = listOfNotNull(result.quality, result.hands).sumOf { it.coverage.requestedSamples }
                if (requested > 0) Text(stringResource(R.string.assistance_coverage, valid, requested), style = MaterialTheme.typography.bodySmall)
            }
        }
        if (!compact) Text(stringResource(R.string.assistance_advisory), style = MaterialTheme.typography.bodySmall)
        if (!sealed) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (!pending && state in setOf(AssistanceStatus.FAILED, AssistanceStatus.UNAVAILABLE, AssistanceStatus.NOT_RUN, AssistanceStatus.PARTIAL) && onRetry != null) {
                TextButton(onClick = onRetry, modifier = Modifier.testTag("btn_retry_assistance")) { Text(stringResource(R.string.assistance_retry)) }
            }
            if (pending && onCancel != null) TextButton(onClick = onCancel) { Text(stringResource(R.string.assistance_cancel)) }
        }
    }
}

private fun sourceTime(ms: Long): String = String.format(Locale.ROOT, "%d:%02d.%03d", ms / 60000, ms / 1000 % 60, ms % 1000)
