package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.data.isEditable
import `in`.kaushalpramaan.app.data.draft.EvidenceDraftState
import `in`.kaushalpramaan.app.data.draft.FinalEvidenceState
import `in`.kaushalpramaan.app.data.draft.SealState
import `in`.kaushalpramaan.app.ui.components.KpBottomBar
import `in`.kaushalpramaan.app.ui.components.KpScaffold
import `in`.kaushalpramaan.app.ui.components.decodeSampledBitmap
import `in`.kaushalpramaan.app.ui.components.defaultMinTapTarget
import `in`.kaushalpramaan.app.ui.components.formatDuration
import `in`.kaushalpramaan.app.ui.components.formatMb
import android.net.Uri
import android.widget.MediaController
import android.widget.VideoView
import androidx.compose.foundation.Image
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Local preview only: photos render via a downsampled Bitmap (never the full-resolution
 * decode), videos play via VideoView streaming directly from the app-private file (never
 * loaded into memory). Retake re-opens the capture screen as a crash-safe replacement of
 * this same item; Delete removes it after an explicit confirmation. */
@Composable
fun EvidencePreviewScreen(
    viewModel: AppViewModel,
    evidenceId: String,
    onBack: () -> Unit,
    onRetake: (taskId: String, oldEvidenceId: String) -> Unit,
    onDeleted: () -> Unit,
) {
    val uiState by viewModel.uiState.collectAsState()
    val evidence = uiState.evidenceByTask.values.flatten().firstOrNull { it.id == evidenceId }
    var showDeleteConfirm by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    val canEdit = evidence != null && uiState.sealState.isEditable() && uiState.taskDrafts[evidence.taskId]?.locked != true && !evidence.fromPreviousRevision

    KpScaffold(
        title = stringResource(R.string.evidence_preview_title),
        language = uiState.language,
        onLanguageChange = viewModel::setLanguage,
        onBack = onBack,
        bottomBar = { KpBottomBar {
            if (canEdit) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                    OutlinedButton(
                        onClick = { onRetake(evidence.taskId, evidence.id) },
                        modifier = Modifier.weight(1f).defaultMinTapTarget().testTag("btn_retake_evidence"),
                    ) { Text(stringResource(R.string.action_retake)) }
                    OutlinedButton(
                        onClick = { showDeleteConfirm = true },
                        modifier = Modifier.weight(1f).defaultMinTapTarget().testTag("btn_delete_evidence"),
                    ) { Text(stringResource(R.string.action_delete)) }
                }
            } else {
                Text(
                    stringResource(R.string.task_detail_sealed_read_only),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        } },
    ) { modifier ->
        if (evidence == null) {
            Column(modifier = modifier.fillMaxSize().padding(16.dp)) {
                Text(stringResource(R.string.loading))
            }
            return@KpScaffold
        }

        Column(modifier = modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
            if (evidence.state == EvidenceDraftState.READY && evidence.finalState == FinalEvidenceState.SEALED) {
                // Plaintext was deleted once sealing succeeded (spec G.5) -- only the
                // encrypted vault copy remains; there is nothing left to preview in-app.
                Text(
                    stringResource(R.string.final_review_item_sealed),
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.testTag("evidence_preview_sealed_notice"),
                )
            } else if (evidence.state == EvidenceDraftState.READY) {
                val file = remember(evidence.relativePath, evidence.finalRelativePath, evidence.finalState) { viewModel.evidenceFile(evidence) }
                if (evidence.kind == EvidenceType.PHOTO) {
                    val bitmap = remember(file) { decodeSampledBitmap(file, 1024, 1024) }
                    bitmap?.let {
                        Image(
                            bitmap = it.asImageBitmap(),
                            contentDescription = stringResource(R.string.content_desc_photo_evidence),
                            modifier = Modifier.fillMaxWidth().aspectRatio(3f / 4f).testTag("evidence_preview_photo"),
                        )
                    }
                } else {
                    AndroidView(
                        factory = { context ->
                            VideoView(context).apply {
                                setVideoURI(Uri.fromFile(file))
                                setMediaController(MediaController(context).also { it.setAnchorView(this) })
                                setOnPreparedListener { player -> player.start() }
                            }
                        },
                        onReset = null, onRelease = { video -> video.stopPlayback() },
                        update = { video ->
                            if (video.tag != file.absolutePath) {
                                video.tag = file.absolutePath
                                video.setVideoURI(Uri.fromFile(file))
                            }
                        },
                        modifier = Modifier.fillMaxWidth().aspectRatio(3f / 4f).testTag("evidence_preview_video"),
                    )
                }
            }

            Text(
                stringResource(R.string.evidence_preview_size_label, formatMb(evidence.finalBytes ?: evidence.byteSize)),
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(top = 12.dp).testTag("evidence_preview_size"),
            )
            (evidence.finalDurationMillis ?: evidence.durationMillis)?.let {
                Text(
                    stringResource(R.string.evidence_preview_duration_label, formatDuration(it)),
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
            if (evidence.widthPx != null && evidence.heightPx != null) {
                Text(
                    stringResource(R.string.evidence_preview_dimensions_label, evidence.widthPx, evidence.heightPx),
                    style = MaterialTheme.typography.bodySmall,
                )
            }

            `in`.kaushalpramaan.app.ui.components.AssistanceCard(
                record = uiState.assistanceByEvidence[evidence.id]?.takeIf {
                    evidence.finalState == FinalEvidenceState.SEALED || it.inputPath == `in`.kaushalpramaan.app.data.assistance.EvidenceAssistanceCoordinator.inputPath(evidence)
                },
                sealed = evidence.finalState == FinalEvidenceState.SEALED,
                onRetry = if (canEdit) ({ viewModel.retryAssistance(evidence.id) }) else null,
                onCancel = if (canEdit) ({ viewModel.cancelAssistance(evidence.id) }) else null,
            )

        }
    }

    if (showDeleteConfirm) {
        AlertDialog(
            onDismissRequest = { showDeleteConfirm = false },
            title = { Text(stringResource(R.string.evidence_delete_confirm_title)) },
            text = { Text(stringResource(R.string.evidence_delete_confirm_body)) },
            confirmButton = {
                TextButton(
                    onClick = {
                        scope.launch {
                            viewModel.deleteEvidence(evidenceId)
                            showDeleteConfirm = false
                            // deleteEvidence's Room suspend calls can resume this coroutine on
                            // Room's own transaction-executor thread rather than Main (observed on
                            // a real device); Navigation's popBackStack() enforces a main-thread
                            // Lifecycle write and crashes otherwise. Force back onto Main explicitly.
                            withContext(Dispatchers.Main.immediate) { onDeleted() }
                        }
                    },
                    modifier = Modifier.testTag("btn_confirm_delete_evidence"),
                ) { Text(stringResource(R.string.action_delete)) }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteConfirm = false }, modifier = Modifier.testTag("btn_cancel_delete_evidence")) {
                    Text(stringResource(R.string.action_cancel))
                }
            },
        )
    }
}
