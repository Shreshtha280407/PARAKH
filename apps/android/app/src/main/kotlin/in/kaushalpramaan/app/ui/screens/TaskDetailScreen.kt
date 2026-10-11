package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.data.draft.EvidenceDraftEntity
import `in`.kaushalpramaan.app.data.draft.EvidenceDraftState
import `in`.kaushalpramaan.app.data.taskTitleRes
import `in`.kaushalpramaan.app.ui.components.KpScaffold
import `in`.kaushalpramaan.app.ui.components.SafetyNoticeCard
import `in`.kaushalpramaan.app.ui.components.defaultMinTapTarget
import `in`.kaushalpramaan.app.ui.components.formatMb
import `in`.kaushalpramaan.app.ui.components.taskStatusText
import android.icu.text.DateFormat
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import java.util.Date
import kotlinx.coroutines.launch

@Composable
fun TaskDetailScreen(
    viewModel: AppViewModel,
    taskId: String,
    onBack: () -> Unit,
    onCapture: (replaceId: String?) -> Unit,
    onPreviewEvidence: (evidenceId: String) -> Unit,
) {
    val uiState by viewModel.uiState.collectAsState()
    val task = remember(taskId) { viewModel.rules.tasksFile.tasks.first { it.id == taskId } }
    val evidenceItems = uiState.evidenceByTask[taskId].orEmpty()
    val taskDraft = uiState.taskDrafts[taskId]
    val usedForTask = uiState.taskEvidenceBytes(taskId)
    val scope = rememberCoroutineScope()
    var pendingDeleteId by remember { mutableStateOf<String?>(null) }

    KpScaffold(
        title = "${task.id} — " + stringResource(taskTitleRes(task.id)),
        language = uiState.language,
        onLanguageChange = viewModel::setLanguage,
        onBack = onBack,
    ) { modifier ->
        Column(modifier = modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
            SafetyNoticeCard()

            Text(
                stringResource(R.string.task_detail_guide_title),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(top = 16.dp, bottom = 4.dp),
            )
            task.stepGuide.forEachIndexed { index, step ->
                Text("${index + 1}. $step", style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(vertical = 2.dp))
            }

            Text(
                stringResource(R.string.task_detail_evidence_hint_title),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(top = 16.dp, bottom = 4.dp),
            )
            Text(task.evidenceHint, style = MaterialTheme.typography.bodyMedium)

            Text(
                stringResource(R.string.task_budget_label, formatMb(usedForTask), formatMb(task.budgetBytes)),
                style = MaterialTheme.typography.titleSmall,
                modifier = Modifier.padding(top = 16.dp),
            )
            LinearProgressIndicator(
                progress = { if (task.budgetBytes > 0) (usedForTask.toFloat() / task.budgetBytes).coerceIn(0f, 1f) else 0f },
                modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
            )
            taskDraft?.let {
                Text(
                    taskStatusText(it.state),
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(top = 4.dp).testTag("task_detail_status"),
                )
            }

            Text(
                stringResource(R.string.task_detail_evidence_title),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(top = 24.dp, bottom = 8.dp),
            )
            if (evidenceItems.isEmpty()) {
                Text(stringResource(R.string.task_detail_no_evidence), style = MaterialTheme.typography.bodyMedium)
            } else {
                evidenceItems.forEachIndexed { index, item ->
                    EvidenceRow(
                        item = item,
                        index = index,
                        onOpen = { if (item.state == EvidenceDraftState.READY) onPreviewEvidence(item.id) },
                        onReplace = { onCapture(item.id) },
                        onRemove = { pendingDeleteId = item.id },
                    )
                }
            }

            OutlinedButton(
                onClick = { onCapture(null) },
                modifier = Modifier.fillMaxWidth().padding(top = 16.dp).defaultMinTapTarget().testTag("btn_add_evidence"),
            ) {
                Text(stringResource(R.string.action_add_evidence))
            }

            Button(
                onClick = onBack,
                modifier = Modifier.fillMaxWidth().padding(top = 16.dp).defaultMinTapTarget().testTag("btn_back_to_tasks"),
            ) {
                Text(stringResource(R.string.action_back_to_tasks))
            }
        }
    }

    pendingDeleteId?.let { deleteId ->
        AlertDialog(
            onDismissRequest = { pendingDeleteId = null },
            title = { Text(stringResource(R.string.evidence_delete_confirm_title)) },
            text = { Text(stringResource(R.string.evidence_delete_confirm_body)) },
            confirmButton = {
                TextButton(
                    onClick = { scope.launch { viewModel.deleteEvidence(deleteId); pendingDeleteId = null } },
                    modifier = Modifier.testTag("btn_confirm_remove_evidence"),
                ) { Text(stringResource(R.string.action_delete)) }
            },
            dismissButton = {
                TextButton(onClick = { pendingDeleteId = null }) { Text(stringResource(R.string.action_cancel)) }
            },
        )
    }
}

@Composable
private fun EvidenceRow(item: EvidenceDraftEntity, index: Int, onOpen: () -> Unit, onReplace: () -> Unit, onRemove: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)
            .let { if (item.state == EvidenceDraftState.READY) it.clickable(onClick = onOpen) else it }
            .testTag("evidence_row"),
    ) {
        Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            val (icon, desc) = if (item.kind == EvidenceType.PHOTO) {
                Icons.Filled.PhotoCamera to stringResource(R.string.content_desc_photo_evidence)
            } else {
                Icons.Filled.Videocam to stringResource(R.string.content_desc_video_evidence)
            }
            Icon(icon, contentDescription = desc)
            Column(modifier = Modifier.padding(start = 12.dp).weight(1f)) {
                when (item.state) {
                    EvidenceDraftState.READY -> {
                        Text(formatMb(item.byteSize), style = MaterialTheme.typography.bodyLarge)
                        Text(
                            DateFormat.getDateTimeInstance().format(Date(item.createdAtMillis)),
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    EvidenceDraftState.STAGING -> Text(stringResource(R.string.task_status_capturing), style = MaterialTheme.typography.bodyLarge)
                    EvidenceDraftState.FAILED -> AssistChip(onClick = onRemove, label = { Text(stringResource(R.string.task_status_failed)) })
                    EvidenceDraftState.DELETED -> Unit
                }
            }
            if (item.state == EvidenceDraftState.READY || item.state == EvidenceDraftState.FAILED) {
                TextButton(
                    onClick = onReplace,
                    modifier = Modifier.defaultMinTapTarget().testTag("btn_replace_evidence_$index"),
                ) {
                    Text(stringResource(R.string.action_replace))
                }
                TextButton(
                    onClick = onRemove,
                    modifier = Modifier.defaultMinTapTarget().testTag("btn_remove_evidence_$index"),
                ) {
                    Text(stringResource(R.string.action_remove))
                }
            }
        }
    }
}
