package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.data.MockEvidence
import `in`.kaushalpramaan.app.data.taskTitleRes
import `in`.kaushalpramaan.app.ui.components.KpScaffold
import `in`.kaushalpramaan.app.ui.components.defaultMinTapTarget
import `in`.kaushalpramaan.app.ui.components.formatMb
import android.icu.text.DateFormat
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
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import java.util.Date

@Composable
fun TaskDetailScreen(viewModel: AppViewModel, taskId: String, onBack: () -> Unit) {
    val uiState by viewModel.uiState.collectAsState()
    val task = remember(taskId) { viewModel.rules.tasksFile.tasks.first { it.id == taskId } }
    val evidenceItems = uiState.evidenceByTask[taskId].orEmpty()
    val usedForTask = uiState.taskEvidenceBytes(taskId)
    val usedTotal = uiState.totalEvidenceBytes()
    val remainingForTask = (task.budgetBytes - usedForTask).coerceAtLeast(0L)
    val remainingOverall = (viewModel.totalBudgetBytes() - usedTotal).coerceAtLeast(0L)

    var showAddDialog by remember { mutableStateOf(false) }
    var replacingId by remember { mutableStateOf<String?>(null) }

    KpScaffold(
        title = "${task.id} — " + stringResource(taskTitleRes(task.id)),
        language = uiState.language,
        onLanguageChange = viewModel::setLanguage,
        onBack = onBack,
    ) { modifier ->
        Column(modifier = modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.Warning, contentDescription = null)
                    Text(
                        stringResource(R.string.task_detail_safety_warning),
                        modifier = Modifier.padding(start = 8.dp),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
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
                        onReplace = { replacingId = item.id; showAddDialog = true },
                        onRemove = { viewModel.removeEvidence(taskId, item.id) },
                    )
                }
            }

            OutlinedButton(
                onClick = { replacingId = null; showAddDialog = true },
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

    if (showAddDialog) {
        val replaceTarget = replacingId?.let { id -> evidenceItems.firstOrNull { it.id == id } }
        val effectiveRemainingForTask = if (replaceTarget != null) remainingForTask + replaceTarget.fakeSizeBytes else remainingForTask
        val effectiveRemainingOverall = if (replaceTarget != null) remainingOverall + replaceTarget.fakeSizeBytes else remainingOverall

        AddEvidenceDialog(
            remainingForTask = effectiveRemainingForTask,
            remainingOverall = effectiveRemainingOverall,
            onDismiss = { showAddDialog = false; replacingId = null },
            onConfirm = { type, size ->
                val now = System.currentTimeMillis()
                val ok = if (replaceTarget != null) {
                    viewModel.replaceEvidence(taskId, replaceTarget.id, type, size, now)
                } else {
                    viewModel.addEvidence(taskId, type, size, now)
                }
                if (ok) {
                    showAddDialog = false
                    replacingId = null
                }
            },
        )
    }
}

@Composable
private fun EvidenceRow(item: MockEvidence, index: Int, onReplace: () -> Unit, onRemove: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp).testTag("evidence_row")) {
        Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            val (icon, desc) = if (item.type == EvidenceType.PHOTO) {
                Icons.Filled.PhotoCamera to stringResource(R.string.content_desc_photo_evidence)
            } else {
                Icons.Filled.Videocam to stringResource(R.string.content_desc_video_evidence)
            }
            Icon(icon, contentDescription = desc)
            Column(modifier = Modifier.padding(start = 12.dp).weight(1f)) {
                Text(formatMb(item.fakeSizeBytes), style = MaterialTheme.typography.bodyLarge)
                Text(
                    DateFormat.getDateTimeInstance().format(Date(item.createdAtMillis)),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
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
