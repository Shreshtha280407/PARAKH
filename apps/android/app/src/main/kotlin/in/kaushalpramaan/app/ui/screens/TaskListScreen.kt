package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.data.taskTitleRes
import `in`.kaushalpramaan.app.ui.components.KpScaffold
import `in`.kaushalpramaan.app.ui.components.defaultMinTapTarget
import `in`.kaushalpramaan.app.ui.components.formatMb
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
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
) {
    val uiState by viewModel.uiState.collectAsState()
    val tasks = viewModel.rules.tasksFile.tasks
    val gapTaskIds = uiState.matchOutput?.applicableTasks
        ?.filter { it.extraEvidenceNeeded }
        ?.mapNotNull { it.task }
        ?.toSet()
        .orEmpty()
    val totalUsed = uiState.totalEvidenceBytes()
    val totalBudget = viewModel.totalBudgetBytes()

    KpScaffold(
        title = stringResource(R.string.tasks_title),
        language = uiState.language,
        onLanguageChange = viewModel::setLanguage,
        onBack = onBack,
    ) { modifier ->
        Column(modifier = modifier.fillMaxSize()) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(stringResource(R.string.tasks_subtitle), style = MaterialTheme.typography.bodyMedium)
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

            LazyColumn(modifier = Modifier.weight(1f).padding(horizontal = 16.dp)) {
                items(tasks, key = { it.id }) { task ->
                    val used = uiState.taskEvidenceBytes(task.id)
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
                                if (task.id in gapTaskIds) {
                                    AssistChip(onClick = { onOpenTask(task.id) }, label = { Text(stringResource(R.string.task_gap_badge)) })
                                }
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
        }
    }
}
