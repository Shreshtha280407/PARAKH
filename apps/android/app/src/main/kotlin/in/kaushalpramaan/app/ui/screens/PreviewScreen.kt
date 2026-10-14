package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.data.draft.EvidenceDraftEntity
import `in`.kaushalpramaan.app.data.draft.FinalEvidenceState
import `in`.kaushalpramaan.app.data.draft.OutboxItemEntity
import `in`.kaushalpramaan.app.data.draft.OutboxItemKind
import `in`.kaushalpramaan.app.data.draft.SealState
import `in`.kaushalpramaan.app.data.draft.SyncState
import `in`.kaushalpramaan.app.data.isEditable
import `in`.kaushalpramaan.app.data.taskTitleRes
import `in`.kaushalpramaan.app.ui.components.KpScaffold
import `in`.kaushalpramaan.app.ui.components.defaultMinTapTarget
import `in`.kaushalpramaan.app.ui.components.formatMb
import `in`.kaushalpramaan.app.data.seal.ProcessOutcome
import `in`.kaushalpramaan.app.data.seal.SealOutcome
import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
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
import kotlinx.coroutines.launch

private fun EvidenceDraftEntity.effectiveBytes(): Long = finalBytes ?: byteSize

/**
 * P5's final evidence-review / seal screen (spec part A) -- replaces P3/P4's placeholder
 * "preview and submit" stand-in. Shows every final item's real optimisation outcome, lets the
 * worker trigger the real automatic-optimisation pass, attest, and seal a real encrypted
 * local package. No bitrate/resolution/JPEG-quality/file-size control is ever exposed here.
 */
@Composable
fun PreviewScreen(
    viewModel: AppViewModel,
    onBack: () -> Unit,
    onEditTask: (String) -> Unit,
    onPreviewEvidence: (String) -> Unit,
    onTrimEvidence: (String) -> Unit,
    onSubmitted: () -> Unit,
) {
    val uiState by viewModel.uiState.collectAsState()
    val tasks = viewModel.rules.tasksFile.tasks
    val scope = rememberCoroutineScope()
    var showDiscardConfirm by remember { mutableStateOf(false) }
    var lastProcessOutcome by remember { mutableStateOf<ProcessOutcome?>(null) }
    var sealErrorMessage by remember { mutableStateOf<Int?>(null) }

    val totalUsed = uiState.totalEvidenceBytes()
    val totalBudget = uiState.debugForcedBudgetBytes ?: viewModel.totalBudgetBytes()
    val sealed = uiState.sealState == SealState.READY_TO_SYNC
    val allProcessed = tasks.all { task ->
        uiState.evidenceByTask[task.id].orEmpty().all { it.finalState != FinalEvidenceState.NOT_PROCESSED }
    }
    val anyOverBudget = tasks.any { task ->
        uiState.evidenceByTask[task.id].orEmpty().any { it.finalState == FinalEvidenceState.QUALITY_FLOOR_EXCEEDED }
    }
    val hasAnyEvidence = tasks.any { uiState.evidenceByTask[it.id].orEmpty().isNotEmpty() }
    val canSeal = uiState.sealState == SealState.FINAL_REVIEW_READY && uiState.attestationConfirmed && !uiState.sealActionInFlight

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
            LinearProgressIndicator(
                progress = { if (totalBudget > 0) (totalUsed.toFloat() / totalBudget).coerceIn(0f, 1f) else 0f },
                modifier = Modifier.fillMaxWidth().padding(top = 4.dp, bottom = 8.dp),
            )

            if (BuildConfigP5ForceOptimizeEnabled()) {
                DebugForcedBudgetControl(
                    currentOverrideMb = uiState.debugForcedBudgetBytes?.let { it / (1024 * 1024) },
                    onSet = { mb -> viewModel.setDebugForcedBudgetBytes(mb?.let { it * 1024L * 1024L }) },
                )
            }

            for (task in tasks) {
                val items = uiState.evidenceByTask[task.id].orEmpty()
                val used = uiState.taskEvidenceBytes(task.id)
                Card(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp).testTag("final_review_task_${task.id}")) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(modifier = Modifier.fillMaxWidth()) {
                            Text(
                                "${task.id} — " + stringResource(taskTitleRes(task.id)),
                                style = MaterialTheme.typography.titleMedium,
                                modifier = Modifier.weight(1f),
                            )
                            TextButton(onClick = { onEditTask(task.id) }, modifier = Modifier.testTag("btn_open_task_${task.id}")) {
                                Text(stringResource(R.string.action_view))
                            }
                        }
                        Text(
                            stringResource(R.string.preview_task_usage, formatMb(used), formatMb(task.budgetBytes)),
                            style = MaterialTheme.typography.bodySmall,
                        )
                        LinearProgressIndicator(
                            progress = { if (task.budgetBytes > 0) (used.toFloat() / task.budgetBytes).coerceIn(0f, 1f) else 0f },
                            modifier = Modifier.fillMaxWidth().padding(top = 4.dp, bottom = 8.dp),
                        )
                        if (items.isEmpty()) {
                            Text(stringResource(R.string.preview_empty_task), style = MaterialTheme.typography.bodySmall)
                        } else {
                            // P7: a task the assessor did NOT reopen for targeted
                            // reassessment stays read-only here too, even while the
                            // assessment overall is editable again -- see
                            // TaskDetailScreen's identical taskLocked check.
                            val taskLocked = uiState.taskDrafts[task.id]?.locked == true
                            items.forEach { item ->
                                FinalReviewItemRow(
                                    item = item,
                                    editable = uiState.sealState.isEditable() && !taskLocked && !item.fromPreviousRevision,
                                    onOpen = { onPreviewEvidence(item.id) },
                                    onTrim = { onTrimEvidence(item.id) },
                                )
                            }
                        }
                    }
                }
            }

            HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))

            when (val outcome = lastProcessOutcome) {
                ProcessOutcome.AllFit -> Text(
                    stringResource(R.string.final_review_optimized_message, formatMb(totalUsed)),
                    color = MaterialTheme.colorScheme.primary,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(bottom = 8.dp).testTag("final_review_optimized_message"),
                )
                ProcessOutcome.SomeItemsExceedBudget -> Text(
                    stringResource(R.string.final_review_item_exceeds_budget),
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(bottom = 8.dp).testTag("final_review_budget_exceeded_message"),
                )
                else -> if (anyOverBudget) {
                    Text(
                        stringResource(R.string.final_review_item_exceeds_budget),
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(bottom = 8.dp),
                    )
                }
            }

            if (uiState.sealState == SealState.DRAFT_EDITABLE || uiState.sealState == SealState.PROCESSING) {
                Button(
                    onClick = {
                        scope.launch {
                            val outcome = viewModel.processEvidence()
                            lastProcessOutcome = outcome
                        }
                    },
                    enabled = hasAnyEvidence && !uiState.sealActionInFlight,
                    modifier = Modifier.fillMaxWidth().defaultMinTapTarget().testTag("btn_optimize_evidence"),
                ) {
                    if (uiState.sealActionInFlight || uiState.sealState == SealState.PROCESSING) {
                        CircularProgressIndicator(modifier = Modifier.padding(end = 8.dp))
                        Text(stringResource(R.string.final_review_optimizing))
                    } else {
                        Text(stringResource(R.string.final_review_action_optimize))
                    }
                }
            }

            if (!sealed) {
                Text(stringResource(R.string.attestation_title), style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 16.dp))
                Row(
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp).defaultMinTapTarget(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Checkbox(
                        checked = uiState.attestationConfirmed,
                        onCheckedChange = { viewModel.setAttestation(it) },
                        enabled = allProcessed && !anyOverBudget,
                        modifier = Modifier.testTag("attestation_checkbox"),
                    )
                    Text(stringResource(R.string.attestation_text), modifier = Modifier.padding(start = 8.dp))
                }
                if (!canSeal) {
                    Text(
                        stringResource(R.string.action_submit_disabled_hint),
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
                sealErrorMessage?.let {
                    Text(stringResource(it), color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 4.dp))
                }
                Button(
                    onClick = {
                        scope.launch {
                            when (val outcome = viewModel.seal()) {
                                SealOutcome.Sealed -> onSubmitted()
                                SealOutcome.ItemsNotReady, SealOutcome.NotReady -> sealErrorMessage = R.string.final_review_item_exceeds_budget
                                SealOutcome.AttestationRequired -> sealErrorMessage = R.string.action_submit_disabled_hint
                                SealOutcome.NoEvidence -> sealErrorMessage = R.string.preview_empty_task
                                SealOutcome.VerificationFailed, SealOutcome.NoActiveAssessment -> sealErrorMessage = R.string.capture_error_finalize_failed
                            }
                        }
                    },
                    enabled = canSeal,
                    modifier = Modifier.fillMaxWidth().padding(top = 16.dp).defaultMinTapTarget().testTag("btn_submit"),
                ) {
                    Text(stringResource(R.string.action_submit))
                }
            } else {
                Text(stringResource(R.string.submitted_body), style = MaterialTheme.typography.titleMedium, modifier = Modifier.testTag("sealed_status_message"))

                SyncStatusSection(
                    viewModel = viewModel,
                    assessmentId = uiState.assessmentDraftId.orEmpty(),
                    syncedAtMillis = uiState.syncedAtMillis,
                )

                if (viewModel.debugExportHooks.isAvailable) {
                    DebugExportCard(viewModel = viewModel, assessmentId = uiState.assessmentDraftId.orEmpty())
                }
                if (BuildConfigP6SyncEndpointOverrideEnabled()) {
                    P6TestOnlySyncEndpointCard(viewModel = viewModel)
                }
                if (uiState.syncedAtMillis == null) {
                    TextButton(
                        onClick = { showDiscardConfirm = true },
                        modifier = Modifier.fillMaxWidth().padding(top = 16.dp).defaultMinTapTarget().testTag("btn_discard_and_reopen"),
                    ) {
                        Text(stringResource(R.string.action_discard_and_reopen), color = MaterialTheme.colorScheme.error)
                    }
                }
            }
        }
    }

    if (showDiscardConfirm) {
        AlertDialog(
            onDismissRequest = { showDiscardConfirm = false },
            title = { Text(stringResource(R.string.discard_reopen_confirm_title)) },
            text = { Text(stringResource(R.string.discard_reopen_confirm_body)) },
            confirmButton = {
                TextButton(
                    onClick = {
                        showDiscardConfirm = false
                        scope.launch { viewModel.discardSealAndReopen() }
                    },
                    modifier = Modifier.testTag("btn_confirm_discard_and_reopen"),
                ) { Text(stringResource(R.string.action_discard_and_reopen)) }
            },
            dismissButton = {
                TextButton(onClick = { showDiscardConfirm = false }) { Text(stringResource(R.string.action_cancel)) }
            },
        )
    }
}

@Composable
private fun FinalReviewItemRow(item: EvidenceDraftEntity, editable: Boolean, onOpen: () -> Unit, onTrim: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp).testTag("final_review_item_${item.id}"),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            if (item.kind == EvidenceType.PHOTO) Icons.Filled.PhotoCamera else Icons.Filled.Videocam,
            contentDescription = null,
        )
        Column(modifier = Modifier.padding(start = 8.dp).weight(1f)) {
            Text(formatMb(item.effectiveBytes()), style = MaterialTheme.typography.bodyMedium)
            Text(
                stringResource(
                    when (item.finalState) {
                        FinalEvidenceState.NOT_PROCESSED -> R.string.final_review_item_not_processed
                        FinalEvidenceState.FITS_AS_IS -> R.string.final_review_item_fits
                        FinalEvidenceState.OPTIMIZED -> R.string.final_review_item_optimized
                        FinalEvidenceState.QUALITY_FLOOR_EXCEEDED -> R.string.final_review_item_exceeds_budget
                        FinalEvidenceState.SEALED -> R.string.final_review_item_sealed
                    },
                ),
                style = MaterialTheme.typography.bodySmall,
                color = if (item.finalState == FinalEvidenceState.QUALITY_FLOOR_EXCEEDED) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        TextButton(onClick = onOpen, modifier = Modifier.defaultMinTapTarget().testTag("btn_view_item_${item.id}")) {
            Text(stringResource(R.string.action_view))
        }
        if (editable && item.kind == EvidenceType.VIDEO && item.finalState != FinalEvidenceState.SEALED) {
            TextButton(onClick = onTrim, modifier = Modifier.defaultMinTapTarget().testTag("btn_trim_item_${item.id}")) {
                Text(stringResource(R.string.action_trim))
            }
        }
    }
}

@Composable
private fun DebugForcedBudgetControl(currentOverrideMb: Long?, onSet: (Long?) -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp).testTag("p5_test_only_force_budget_card")) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                stringResource(R.string.p5_test_only_force_budget_label, currentOverrideMb?.let { "$it MB" } ?: "off"),
                style = MaterialTheme.typography.bodySmall,
            )
            Row(modifier = Modifier.padding(top = 8.dp)) {
                OutlinedButton(onClick = { onSet(1L) }, modifier = Modifier.testTag("btn_force_budget_1mb")) { Text("1 MB") }
                OutlinedButton(onClick = { onSet(null) }, modifier = Modifier.padding(start = 8.dp).testTag("btn_force_budget_off")) { Text(stringResource(R.string.action_cancel)) }
            }
        }
    }
}

@Composable
private fun BuildConfigP5ForceOptimizeEnabled(): Boolean = `in`.kaushalpramaan.app.BuildConfig.P5_TEST_ONLY_FORCE_OPTIMIZE_ENABLED

/** P5_TEST_ONLY debug-only verification export (spec part H) -- only ever rendered when
 * [AppViewModel.debugExportHooks] reports available, which is only ever true in a debug
 * build (app/src/release's factory always returns an unavailable no-op). */
@Composable
private fun DebugExportCard(viewModel: AppViewModel, assessmentId: String) {
    val scope = rememberCoroutineScope()
    var summary by remember { mutableStateOf<`in`.kaushalpramaan.app.debug.DebugExportSummary?>(null) }
    var exporting by remember { mutableStateOf(false) }

    Card(modifier = Modifier.fillMaxWidth().padding(top = 16.dp).testTag("p5_test_only_debug_export_card")) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(stringResource(R.string.p5_test_only_debug_export_title), style = MaterialTheme.typography.titleSmall)
            Button(
                onClick = {
                    scope.launch {
                        exporting = true
                        summary = viewModel.debugExportHooks.export(assessmentId)
                        exporting = false
                    }
                },
                enabled = !exporting,
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp).testTag("btn_debug_export"),
            ) { Text(stringResource(R.string.p5_test_only_debug_export_action)) }

            summary?.let { s ->
                Text(
                    stringResource(
                        R.string.p5_test_only_debug_export_result,
                        s.signatureVerified.toString(),
                        s.items.size,
                        s.allHashesMatch.toString(),
                    ),
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(top = 8.dp).testTag("debug_export_result"),
                )
                TextButton(
                    onClick = {
                        viewModel.debugExportHooks.cleanup(assessmentId)
                        summary = null
                    },
                    modifier = Modifier.testTag("btn_debug_export_cleanup"),
                ) { Text(stringResource(R.string.p5_test_only_debug_export_cleanup_action)) }
            }
        }
    }
}

/** P6: functional sync state/progress display (spec requirement -- "no visual redesign
 * required"), reading [AppViewModel.observeOutbox]'s live Room flow directly -- never a
 * locally-faked state, same discipline as the seal-state mirror above. */
@Composable
private fun SyncStatusSection(viewModel: AppViewModel, assessmentId: String, syncedAtMillis: Long?) {
    val outboxItems by viewModel.observeOutbox(assessmentId).collectAsState(initial = emptyList<OutboxItemEntity>())

    Card(modifier = Modifier.fillMaxWidth().padding(top = 16.dp).testTag("sync_status_card")) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(stringResource(R.string.sync_section_title), style = MaterialTheme.typography.titleMedium)

            if (syncedAtMillis != null) {
                Text(
                    stringResource(R.string.sync_overall_synced),
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(top = 8.dp).testTag("sync_overall_synced"),
                )
            } else {
                val doneCount = outboxItems.count { it.syncState == SyncState.SYNCED }
                val total = outboxItems.size
                Text(
                    if (total > 0) stringResource(R.string.sync_overall_in_progress, doneCount, total)
                    else stringResource(R.string.sync_overall_not_started),
                    modifier = Modifier.padding(top = 8.dp).testTag("sync_overall_status"),
                )

                for (item in outboxItems.sortedBy { it.priority }) {
                    SyncItemRow(item)
                }

                Button(
                    onClick = { viewModel.syncNow() },
                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp).defaultMinTapTarget().testTag("btn_sync_now"),
                ) {
                    Text(stringResource(R.string.sync_action_sync_now))
                }
            }
        }
    }
}

@Composable
private fun SyncItemRow(item: OutboxItemEntity) {
    val label = if (item.kind == OutboxItemKind.MANIFEST) {
        stringResource(R.string.sync_item_manifest_label)
    } else {
        item.taskId.orEmpty()
    }
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp).testTag("sync_item_${item.id}"),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(label, style = MaterialTheme.typography.bodyMedium)
            Text(
                when (item.syncState) {
                    SyncState.QUEUED -> stringResource(R.string.sync_state_queued)
                    SyncState.WAITING_FOR_NETWORK -> stringResource(R.string.sync_state_waiting_for_network)
                    SyncState.UPLOADING -> stringResource(R.string.sync_state_uploading, formatMb(item.bytesUploaded))
                    SyncState.RETRYING -> stringResource(R.string.sync_state_retrying, item.retryCount)
                    SyncState.VERIFYING -> stringResource(R.string.sync_state_verifying)
                    SyncState.SYNCED -> stringResource(R.string.sync_state_synced)
                    SyncState.FAILED_ACTION_REQUIRED -> stringResource(R.string.sync_state_failed_action_required)
                },
                style = MaterialTheme.typography.bodySmall,
                color = if (item.syncState == SyncState.FAILED_ACTION_REQUIRED) {
                    MaterialTheme.colorScheme.error
                } else {
                    MaterialTheme.colorScheme.onSurfaceVariant
                },
            )
        }
    }
}

private fun BuildConfigP6SyncEndpointOverrideEnabled(): Boolean =
    `in`.kaushalpramaan.app.BuildConfig.P6_TEST_ONLY_SYNC_ENDPOINT_OVERRIDE_ENABLED

/** P6_TEST_ONLY, debug builds only: lets the manual-gate tester point sync at their laptop's
 * real LAN IP at runtime, no rebuild -- see SyncEndpointConfig/DebugOverridableSyncEndpointConfig
 * (app/src/debug). Genuinely absent from release (see
 * app/build.gradle.kts's verifyP6SyncEndpointOverrideAbsentFromRelease). */
@Composable
private fun P6TestOnlySyncEndpointCard(viewModel: AppViewModel) {
    var text by remember { mutableStateOf(viewModel.syncEndpointConfig.baseUrl()) }
    Card(modifier = Modifier.fillMaxWidth().padding(top = 12.dp).testTag("p6_test_only_sync_endpoint_card")) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(stringResource(R.string.p6_test_only_sync_url_label), style = MaterialTheme.typography.bodySmall)
            androidx.compose.material3.OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                placeholder = { Text(stringResource(R.string.p6_test_only_sync_url_hint)) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp).testTag("p6_test_only_sync_url_field"),
            )
            Button(
                onClick = { viewModel.syncEndpointConfig.setOverrideBaseUrl(text) },
                modifier = Modifier.padding(top = 8.dp).testTag("btn_p6_test_only_save_sync_url"),
            ) { Text(stringResource(R.string.p6_test_only_sync_url_save)) }
        }
    }
}
