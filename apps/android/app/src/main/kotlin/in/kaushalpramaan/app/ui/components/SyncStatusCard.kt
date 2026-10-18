package `in`.kaushalpramaan.app.ui.components

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.data.draft.SealState
import `in`.kaushalpramaan.app.data.sync.SyncWorker
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.CloudUpload
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.flowOf

@Composable
fun AssessmentSyncStatus(viewModel: AppViewModel, modifier: Modifier = Modifier) {
    val state by viewModel.uiState.collectAsState()
    val context = LocalContext.current.applicationContext
    val assessment = state.assessmentDraftId.orEmpty()
    val revision = state.revisionId.orEmpty()
    val sealed = state.sealState == SealState.READY_TO_SYNC
    val rows by remember(viewModel, assessment) { viewModel.observeOutbox(assessment) }.collectAsState(initial = emptyList())
    val work by remember(context, assessment, revision) {
        if (assessment.isNotEmpty() && revision.isNotEmpty()) SyncWorker.observeWorkInfoFlow(context, assessment, revision) else flowOf(emptyList())
    }.collectAsState(initial = emptyList())
    val current = work.firstOrNull { !it.state.isFinished } ?: work.maxByOrNull { it.outputData.getLong(SyncWorker.KEY_STARTED_AT, 0) }
    val connection = rememberConnectionStatus()
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(sealed, state.syncedAtMillis) {
        while (sealed && state.syncedAtMillis == null) { now = System.currentTimeMillis(); delay(1000) }
    }
    val latestActivity = maxOf(current?.progress?.getLong(SyncWorker.KEY_STARTED_AT, 0) ?: 0L,
        rows.maxOfOrNull { it.lastAttemptAtMillis ?: 0L } ?: 0L)
    val presentation = syncPresentation(sealed, state.syncedAtMillis != null, connection.internetAvailable,
        rows, state.evidenceByTask.values.flatten(), current?.state, current?.runAttemptCount ?: 0,
        latestActivity, now)
    val lifecycle by LocalLifecycleOwner.current.lifecycle.currentStateFlow.collectAsState()
    var notice by remember(assessment, revision) { mutableStateOf<SyncPhase?>(null) }
    LaunchedEffect(presentation.phase, lifecycle, revision, current?.id, current?.state) {
        if (sealed && revision.isNotEmpty() && lifecycle == Lifecycle.State.RESUMED &&
            (presentation.phase == SyncPhase.SUBMITTED || presentation.phase == SyncPhase.STALLED ||
                presentation.problem && current?.state == androidx.work.WorkInfo.State.FAILED)) {
            val category = if (presentation.phase == SyncPhase.SUBMITTED) "complete" else "problem/${current?.id}"
            if (viewModel.claimSyncNotice("$assessment/$revision/$category")) notice = presentation.phase
        }
        // A popup from an earlier problem must not cover a new successful state.
        if (presentation.phase == SyncPhase.SUBMITTED && notice != null) notice = SyncPhase.SUBMITTED
    }
    SyncStatusContent(presentation, onRetry = { viewModel.syncNow(presentation.phase == SyncPhase.STALLED) }, modifier = modifier)
    notice?.let { phase ->
        AlertDialog(onDismissRequest = { notice = null },
            title = { Text(stringResource(phase.titleResource())) },
            text = { Text(stringResource(phase.bodyResource())) },
            confirmButton = {
                TextButton(onClick = { notice = null; if (phase != SyncPhase.SUBMITTED) viewModel.syncNow(phase == SyncPhase.STALLED) }, modifier = Modifier.testTag("sync_notice_confirm")) {
                    Text(stringResource(if (phase == SyncPhase.SUBMITTED) R.string.sync_notice_done else R.string.sync_action_retry))
                }
            },
            dismissButton = { if (phase != SyncPhase.SUBMITTED) TextButton(onClick = { notice = null }, modifier = Modifier.testTag("sync_notice_dismiss")) { Text(stringResource(R.string.sync_notice_later)) } },
            modifier = Modifier.testTag("sync_status_notice"))
    }
}

@Composable
fun SyncStatusContent(status: SyncPresentation, onRetry: () -> Unit, modifier: Modifier = Modifier) {
    val complete = status.phase == SyncPhase.SUBMITTED
    val accent = if (complete) MaterialTheme.colorScheme.tertiary else if (status.problem) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary
    Surface(modifier.fillMaxWidth().testTag("sync_status_card").semantics { liveRegion = LiveRegionMode.Polite },
        shape = RoundedCornerShape(14.dp), color = MaterialTheme.colorScheme.surfaceContainer,
        border = BorderStroke(1.dp, accent.copy(alpha = .55f))) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                if (status.active) SyncActivityIndicator(accent)
                else Icon(if (complete) Icons.Filled.CheckCircle else if (status.problem) Icons.Filled.ErrorOutline else Icons.Filled.CloudUpload, null, tint = accent)
                Text(stringResource(status.phase.titleResource()), style = MaterialTheme.typography.titleMedium, color = accent,
                    modifier = Modifier.testTag(if (complete) "sync_overall_synced" else "sync_overall_status"))
            }
            Text(stringResource(status.phase.bodyResource()), style = MaterialTheme.typography.bodyMedium)
            if (status.phase != SyncPhase.BEFORE_SEAL) {
                if (status.active && status.uploadedBytes == 0L) LinearProgressIndicator(Modifier.fillMaxWidth().testTag("sync_progress_active"))
                else LinearProgressIndicator(progress = { status.fraction }, modifier = Modifier.fillMaxWidth().testTag("sync_progress"), color = accent)
                if (!complete && status.totalBytes > 0) Text(stringResource(R.string.sync_uploaded_bytes, formatTransferBytes(status.uploadedBytes), formatTransferBytes(status.totalBytes)), style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("sync_uploaded_bytes"))
                if (!complete && status.totalItems > 0) Text(stringResource(R.string.sync_verified_items, status.completedItems, status.totalItems), style = MaterialTheme.typography.bodySmall)
                if (!complete) {
                    Text(stringResource(R.string.sync_keep_local), style = MaterialTheme.typography.bodySmall)
                    KpButton(onClick = onRetry, enabled = !status.active, modifier = Modifier.fillMaxWidth().testTag("btn_sync_now")) {
                        Text(stringResource(if (status.active) R.string.sync_upload_running else R.string.sync_action_retry))
                    }
                }
            }
        }
    }
}

/** Sync activity must remain visible even when the device disables UI transition
 * animations. Frame timestamps drive only this spinner; byte progress stays real. */
@Composable
private fun SyncActivityIndicator(color: Color) {
    val rotation = remember { mutableFloatStateOf(0f) }
    LaunchedEffect(Unit) {
        val start = withFrameNanos { it }
        while (true) {
            withFrameNanos { frame -> rotation.floatValue = ((frame - start) % 1_000_000_000L) / 1_000_000_000f * 360f }
        }
    }
    Canvas(Modifier.size(24.dp).testTag("sync_activity_indicator").semantics {
        progressBarRangeInfo = ProgressBarRangeInfo.Indeterminate
    }) {
        val width = 2.dp.toPx()
        drawArc(color, startAngle = rotation.floatValue - 90f, sweepAngle = 270f, useCenter = false,
            topLeft = Offset(width / 2, width / 2), size = Size(size.width - width, size.height - width),
            style = Stroke(width, cap = StrokeCap.Round))
    }
}

private fun SyncPhase.titleResource(): Int = when (this) {
    SyncPhase.BEFORE_SEAL -> R.string.sync_before_seal_title
    SyncPhase.OFFLINE -> R.string.sync_offline_title
    SyncPhase.QUEUED -> R.string.sync_queued_title
    SyncPhase.UPLOADING -> R.string.sync_uploading_title
    SyncPhase.VERIFYING -> R.string.sync_verifying_title
    SyncPhase.RETRYING -> R.string.sync_retrying_title
    SyncPhase.FAILED -> R.string.sync_failed_title
    SyncPhase.STALLED -> R.string.sync_stalled_title
    SyncPhase.SUBMITTED -> R.string.sync_overall_synced
}
private fun SyncPhase.bodyResource(): Int = when (this) {
    SyncPhase.BEFORE_SEAL -> R.string.sync_before_seal_body
    SyncPhase.OFFLINE -> R.string.sync_offline_body
    SyncPhase.QUEUED -> R.string.sync_queued_body
    SyncPhase.UPLOADING -> R.string.sync_uploading_body
    SyncPhase.VERIFYING -> R.string.sync_verifying_body
    SyncPhase.RETRYING -> R.string.sync_retrying_body
    SyncPhase.FAILED -> R.string.sync_failed_body
    SyncPhase.STALLED -> R.string.sync_stalled_body
    SyncPhase.SUBMITTED -> R.string.sync_complete_body
}
