package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.ui.components.defaultMinTapTarget
import `in`.kaushalpramaan.app.ui.components.formatMb
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp

/** Shared dialog for both "add evidence" and "replace evidence" -- a fake
 * byte size is chosen with a slider bounded by whatever remains of the
 * task/total budget, matching the "configurable fake byte sizes" P-3
 * requirement without any real camera/file access. */
@Composable
fun AddEvidenceDialog(
    remainingForTask: Long,
    remainingOverall: Long,
    onDismiss: () -> Unit,
    onConfirm: (EvidenceType, Long) -> Unit,
) {
    var type by remember { mutableStateOf(EvidenceType.PHOTO) }
    val maxAllowed = minOf(remainingForTask, remainingOverall).coerceAtLeast(0L)
    var sizeBytes by remember { mutableStateOf((maxAllowed / 2).coerceAtLeast(0L)) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.add_evidence_title)) },
        text = {
            Column {
                Text(stringResource(R.string.add_evidence_type_label), style = MaterialTheme.typography.titleSmall)
                Row(modifier = Modifier.padding(top = 8.dp, bottom = 16.dp)) {
                    FilterChip(
                        selected = type == EvidenceType.PHOTO,
                        onClick = { type = EvidenceType.PHOTO },
                        label = { Text(stringResource(R.string.evidence_type_photo)) },
                        modifier = Modifier.defaultMinTapTarget().testTag("evidence_type_photo"),
                    )
                    FilterChip(
                        selected = type == EvidenceType.VIDEO,
                        onClick = { type = EvidenceType.VIDEO },
                        label = { Text(stringResource(R.string.evidence_type_video)) },
                        modifier = Modifier.padding(start = 8.dp).defaultMinTapTarget().testTag("evidence_type_video"),
                    )
                }

                if (maxAllowed <= 0L) {
                    Text(
                        stringResource(R.string.add_evidence_error_task_budget),
                        color = MaterialTheme.colorScheme.error,
                    )
                } else {
                    Text(stringResource(R.string.add_evidence_size_label, formatMb(sizeBytes)))
                    Slider(
                        value = sizeBytes.toFloat(),
                        onValueChange = { sizeBytes = it.toLong() },
                        valueRange = 0f..maxAllowed.toFloat(),
                        modifier = Modifier.fillMaxWidth().defaultMinTapTarget().testTag("evidence_size_slider"),
                    )
                    Text(
                        stringResource(R.string.add_evidence_remaining_task, formatMb(remainingForTask)),
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Text(
                        stringResource(R.string.add_evidence_remaining_total, formatMb(remainingOverall)),
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onConfirm(type, sizeBytes) },
                enabled = maxAllowed > 0L && sizeBytes > 0L,
                modifier = Modifier.testTag("btn_save_evidence"),
            ) {
                Text(stringResource(R.string.action_save))
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, modifier = Modifier.testTag("btn_cancel_evidence_dialog")) {
                Text(stringResource(R.string.action_cancel))
            }
        },
    )
}
