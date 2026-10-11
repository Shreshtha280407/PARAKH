package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.data.taskTitleRes
import `in`.kaushalpramaan.app.ui.components.KpScaffold
import `in`.kaushalpramaan.app.ui.components.SafetyNoticeCard
import `in`.kaushalpramaan.app.ui.components.defaultMinTapTarget
import `in`.kaushalpramaan.app.ui.components.formatMb
import `in`.kaushalpramaan.app.ui.components.taskStatusText
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp

@Composable
fun TaskListScreen(
    viewModel: AppViewModel,
    onBack: () -> Unit,
    onOpenTask: (String) -> Unit,
    onPreview: () -> Unit,
    onDraftDeleted: () -> Unit,
) {
    val uiState by viewModel.uiState.collectAsState()
    val tasks = viewModel.rules.tasksFile.tasks
    val totalUsed = uiState.totalEvidenceBytes()
    val totalBudget = viewModel.totalBudgetBytes()
    var showDeleteDraftConfirm by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) { viewModel.startOrResumeAssessmentDraft() }

    KpScaffold(
        title = stringResource(R.string.tasks_title),
        language = uiState.language,
        onLanguageChange = viewModel::setLanguage,
        onBack = onBack,
    ) { modifier ->
        Column(modifier = modifier.fillMaxSize()) {
            Column(modifier = Modifier.padding(16.dp)) {
                SafetyNoticeCard()
                if (uiState.assessmentIsTestOnly) {
                    Text(
                        stringResource(R.string.p4_test_only_badge),
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.padding(top = 8.dp).testTag("p4_test_only_badge"),
                    )
                }
                Text(
                    stringResource(R.string.tasks_subtitle),
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(top = 12.dp),
                )
                Text(
                    stringResource(R.string.tasks_budget_total, formatMb(totalUsed), formatMb(totalBudget)),
                    style = MaterialTheme.typography.titleSmall,
                    modifier = Modifier.padding(top = 8.dp),
                )
                LinearProgressIndicator(
                    progress = { if (totalBudget > 0) (totalUsed.toFloat() / totalBudget).coerceIn(0f, 1f) else 0f },
                    modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                )
            }

            LazyColumn(
                modifier = Modifier.weight(1f).padding(horizontal = 16.dp).testTag("task_list_lazy_column"),
            ) {
                items(tasks, key = { it.id }) { task ->
                    val used = uiState.taskEvidenceBytes(task.id)
                    val draft = uiState.taskDrafts[task.id]
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 6.dp)
                            .clickable { onOpenTask(task.id) }
                            .defaultMinTapTarget()
                            .testTag("task_card_${task.id}"),
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Row(modifier = Modifier.fillMaxWidth()) {
                                Text(
                                    "${task.id} — " + stringResource(taskTitleRes(task.id)),
                                    style = MaterialTheme.typography.titleMedium,
                                    modifier = Modifier.weight(1f),
                                )
                                if (task.id in uiState.gapTaskIds) {
                                    AssistChip(
                                        onClick = { onOpenTask(task.id) },
                                        label = { Text(stringResource(R.string.task_gap_badge)) },
                                        modifier = Modifier.testTag("task_gap_badge_${task.id}"),
                                    )
                                }
                            }
                            draft?.let {
                                Text(
                                    taskStatusText(it.state) + " · " + stringResource(R.string.task_evidence_count_label, it.evidenceCount),
                                    style = MaterialTheme.typography.bodySmall,
                                    modifier = Modifier.padding(top = 4.dp).testTag("task_status_${task.id}"),
                                )
                            }
                            Text(
                                stringResource(R.string.task_budget_label, formatMb(used), formatMb(task.budgetBytes)),
                                style = MaterialTheme.typography.bodySmall,
                                modifier = Modifier.padding(top = 4.dp),
                            )
                            LinearProgressIndicator(
                                progress = { if (task.budgetBytes > 0) (used.toFloat() / task.budgetBytes).coerceIn(0f, 1f) else 0f },
                                modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                            )
                        }
                    }
                }
            }

            Button(
                onClick = onPreview,
                modifier = Modifier.fillMaxWidth().padding(16.dp).defaultMinTapTarget().testTag("btn_preview"),
            ) {
                Text(stringResource(R.string.action_preview))
            }

            if (uiState.assessmentIsTestOnly && uiState.assessmentDraftId != null) {
                TextButton(
                    onClick = { showDeleteDraftConfirm = true },
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp).defaultMinTapTarget().testTag("btn_delete_test_draft"),
                ) {
                    Text(stringResource(R.string.action_delete_test_draft), color = MaterialTheme.colorScheme.error)
                }
            }
        }
    }

    if (showDeleteDraftConfirm) {
        AlertDialog(
            onDismissRequest = { showDeleteDraftConfirm = false },
            title = { Text(stringResource(R.string.delete_draft_confirm_title)) },
            text = { Text(stringResource(R.string.delete_draft_confirm_body)) },
            confirmButton = {
                TextButton(
                    onClick = {
                        showDeleteDraftConfirm = false
                        viewModel.deleteCurrentAssessmentDraft(onDone = onDraftDeleted)
                    },
                    modifier = Modifier.testTag("btn_confirm_delete_test_draft"),
                ) { Text(stringResource(R.string.action_delete)) }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteDraftConfirm = false }) { Text(stringResource(R.string.action_cancel)) }
            },
        )
    }
}
