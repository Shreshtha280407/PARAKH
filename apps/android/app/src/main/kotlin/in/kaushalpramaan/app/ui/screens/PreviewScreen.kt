package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.data.SubmissionState
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp

@Composable
fun PreviewScreen(
    viewModel: AppViewModel,
    onBack: () -> Unit,
    onEditTask: (String) -> Unit,
    onSubmitted: () -> Unit,
) {
    val uiState by viewModel.uiState.collectAsState()
    val tasks = viewModel.rules.tasksFile.tasks
    val totalUsed = uiState.totalEvidenceBytes()
    val totalBudget = viewModel.totalBudgetBytes()
    val sealed = uiState.submissionState == SubmissionState.SEALED_LOCALLY

    KpScaffold(
        title = stringResource(R.string.preview_title),
        language = uiState.language,
        onLanguageChange = viewModel::setLanguage,
        onBack = onBack,
    ) { modifier ->
        Column(modifier = modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
            Text(
                stringResource(R.string.preview_total_usage, formatMb(totalUsed), formatMb(totalBudget)),
                style = MaterialTheme.typography.titleMedium,
            )

            for (task in tasks) {
                val items = uiState.evidenceByTask[task.id].orEmpty()
                val used = uiState.taskEvidenceBytes(task.id)
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 6.dp)
                        .let { if (!sealed) it.clickable { onEditTask(task.id) } else it }
                        .defaultMinTapTarget(),
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text("${task.id} — " + stringResource(taskTitleRes(task.id)), style = MaterialTheme.typography.titleMedium)
                        Text(
                            stringResource(R.string.preview_task_usage, formatMb(used), formatMb(task.budgetBytes)),
                            style = MaterialTheme.typography.bodySmall,
                        )
                        if (items.isEmpty()) {
                            Text(stringResource(R.string.preview_empty_task), style = MaterialTheme.typography.bodySmall)
                        } else {
                            Text("${items.size} item(s)", style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }

            HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))

            if (!sealed) {
                Text(stringResource(R.string.attestation_title), style = MaterialTheme.typography.titleMedium)
                Row(
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp).defaultMinTapTarget(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Checkbox(
                        checked = uiState.attestationChecked,
                        onCheckedChange = viewModel::setAttestation,
                        modifier = Modifier.testTag("attestation_checkbox"),
                    )
                    Text(stringResource(R.string.attestation_text), modifier = Modifier.padding(start = 8.dp))
                }
                if (!uiState.attestationChecked) {
                    Text(
                        stringResource(R.string.action_submit_disabled_hint),
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
                Button(
                    onClick = {
                        viewModel.submit()
                        onSubmitted()
                    },
                    enabled = uiState.attestationChecked,
                    modifier = Modifier.fillMaxWidth().padding(top = 16.dp).defaultMinTapTarget().testTag("btn_submit"),
                ) {
                    Text(stringResource(R.string.action_submit))
                }
            } else {
                Text(stringResource(R.string.submitted_title), style = MaterialTheme.typography.titleMedium)
            }
        }
    }
}
