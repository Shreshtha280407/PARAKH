package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.data.isEditable
import `in`.kaushalpramaan.app.data.draft.EvidenceDraftEntity
import `in`.kaushalpramaan.app.data.draft.EvidenceDraftState
import `in`.kaushalpramaan.app.data.draft.FinalEvidenceState
import `in`.kaushalpramaan.app.data.draft.SealState
import `in`.kaushalpramaan.app.data.taskTitleRes
import `in`.kaushalpramaan.app.ui.components.KpBottomBar
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
import `in`.kaushalpramaan.app.ui.components.KpButton as Button
import `in`.kaushalpramaan.app.ui.components.KpCard as Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import `in`.kaushalpramaan.app.ui.components.KpOutlinedButton as OutlinedButton
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
    // Once sealing has started, evidence is immutable in normal worker flow (spec part E.3)
    // -- edits are only possible again via an explicit discard/reopen from the final review
    // screen, never silently here. P7: a task the assessor did NOT reopen for targeted
    // reassessment stays locked even while the assessment as a whole is editable again --
    // see TaskDraftEntity.locked's doc comment; this is the UI's own affordance, the real
    // enforcement is server-side (routers/uploads.py).
    val taskLocked = taskDraft?.locked == true
    val editable = uiState.sealState.isEditable() && !taskLocked
    val isReopenedForReassessment = taskId in uiState.pendingReassessmentTaskCodes

    KpScaffold(
        title = "${task.id} — " + stringResource(taskTitleRes(task.id)),
        language = uiState.language,
        onLanguageChange = viewModel::setLanguage,
        onBack = onBack,
        bottomBar = { KpBottomBar {
            if (editable) {
                OutlinedButton(
                    onClick = { onCapture(null) },
                    modifier = Modifier.fillMaxWidth().defaultMinTapTarget().testTag("btn_add_evidence"),
                ) {
                    Text(stringResource(R.string.action_add_evidence))
                }
            } else if (!taskLocked) {
                Text(
                    stringResource(R.string.task_detail_sealed_read_only),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.testTag("task_detail_sealed_read_only"),
                )
            }

            Button(
                onClick = onBack,
                modifier = Modifier.fillMaxWidth().defaultMinTapTarget().testTag("btn_back_to_tasks"),
            ) {
                Text(stringResource(R.string.action_back_to_tasks))
            }
        } },
    ) { modifier ->
        Column(modifier = modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
            SafetyNoticeCard()

            if (isReopenedForReassessment) {
                Card(
                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp).testTag("reassessment_banner"),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text(
                            stringResource(R.string.reassessment_banner_title),
                            style = MaterialTheme.typography.titleSmall,
                        )
                        uiState.pendingReassessmentReason?.let {
                            Text(
                                stringResource(R.string.reassessment_banner_reason, it),
                                style = MaterialTheme.typography.bodyMedium,
                                modifier = Modifier.padding(top = 4.dp),
                            )
                        }
                        uiState.pendingReassessmentCaptureInstructions?.let {
                            Text(
                                stringResource(R.string.reassessment_banner_instructions, it),
                                style = MaterialTheme.typography.bodyMedium,
                                modifier = Modifier.padding(top = 4.dp).testTag("reassessment_capture_instructions"),
                            )
                        }
                    }
                }
            } else if (taskLocked) {
                Text(
                    stringResource(R.string.task_detail_locked_pending_other_task),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(top = 12.dp).testTag("task_detail_locked_pending_other_task"),
                )
            }

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
                    val previouslySubmitted = item.fromPreviousRevision ||
                        (taskLocked && item.finalState == FinalEvidenceState.SEALED)
                    EvidenceRow(
                        item = item,
                        index = index,
                        editable = editable,
                        previouslySubmitted = previouslySubmitted,
                        onOpen = { if (item.state == EvidenceDraftState.READY && !previouslySubmitted) onPreviewEvidence(item.id) },
                        onReplace = { onCapture(item.id) },
                        onRemove = { pendingDeleteId = item.id },
                    )
                }
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
private fun EvidenceRow(item: EvidenceDraftEntity, index: Int, editable: Boolean, previouslySubmitted: Boolean, onOpen: () -> Unit, onReplace: () -> Unit, onRemove: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)
            .let { if (item.state == EvidenceDraftState.READY && !previouslySubmitted) it.clickable(onClick = onOpen) else it }
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
                        // P7: a superseded prior-revision item has no local file left to
                        // preview (P6 deletes the vault copy right after its server receipt)
                        // -- say so honestly instead of offering a preview that cannot exist.
                        if (previouslySubmitted) {
                            Text(
                                stringResource(R.string.evidence_from_previous_revision),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.error,
                                modifier = Modifier.testTag("evidence_from_previous_revision_$index"),
                            )
                        }
                    }
                    EvidenceDraftState.STAGING -> Text(stringResource(R.string.task_status_capturing), style = MaterialTheme.typography.bodyLarge)
                    EvidenceDraftState.FAILED -> AssistChip(onClick = onRemove, label = { Text(stringResource(R.string.task_status_failed)) })
                    EvidenceDraftState.DELETED -> Unit
                }
            }
            if (editable && !previouslySubmitted && (item.state == EvidenceDraftState.READY || item.state == EvidenceDraftState.FAILED)) {
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
