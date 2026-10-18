package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.BuildConfig
import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.capture.CaptureMode
import `in`.kaushalpramaan.app.capture.CaptureSession
import `in`.kaushalpramaan.app.capture.PhotoResult
import `in`.kaushalpramaan.app.capture.VideoQualityChoice
import `in`.kaushalpramaan.app.capture.VideoResult
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.data.taskTitleRes
import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.data.draft.BeginCaptureResult
import `in`.kaushalpramaan.app.data.draft.CaptureRejectionReason
import `in`.kaushalpramaan.app.data.draft.EvidenceRepository
import `in`.kaushalpramaan.app.data.draft.FinalizeResult
import `in`.kaushalpramaan.app.ui.components.defaultMinTapTarget
import `in`.kaushalpramaan.app.ui.components.formatMb
import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import android.util.Log
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.view.PreviewView
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.FiberManualRecord
import androidx.compose.material3.*
import androidx.compose.ui.Alignment
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import `in`.kaushalpramaan.app.ui.components.KpButton as Button
import `in`.kaushalpramaan.app.ui.components.KpFilterChip as FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import `in`.kaushalpramaan.app.ui.components.KpOutlinedButton as OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private enum class PermissionState { UNKNOWN, GRANTED, DENIED }

/** Structured, content-free diagnostic tag: only safe technical state (task id, lifecycle
 * state, byte counts, error categories) is ever logged here -- never a file path, media
 * content, or personal information. */
private const val LOG_TAG = "KP-Capture"

@Composable
fun CaptureScreen(
    viewModel: AppViewModel,
    taskId: String,
    replacesEvidenceId: String?,
    onDone: () -> Unit,
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val scope = rememberCoroutineScope()

    var mode by remember { mutableStateOf(CaptureMode.PHOTO) }
    var quality by remember { mutableStateOf(VideoQualityChoice.SD) }
    var debugCeilingRequested by remember { mutableStateOf(false) }
    var permissionState by remember { mutableStateOf(PermissionState.UNKNOWN) }
    var canAskAgain by remember { mutableStateOf(true) }
    var statusMessageRes by remember { mutableStateOf<Int?>(null) }
    var isRecording by remember { mutableStateOf(false) }
    // True from the moment beginCapture() is called until finalizeCapture() returns, for
    // EITHER photo or video -- the single owner of that evidence row's next write for the
    // whole window. Back/cancel must never write to (or delete) that row concurrently; see
    // cleanupActiveCapture() below for why.
    var captureInFlight by remember { mutableStateOf(false) }
    var activeEvidenceId by remember { mutableStateOf<String?>(null) }
    var ceilingBytes by remember { mutableLongStateOf(0L) }
    var bytesRecorded by remember { mutableLongStateOf(0L) }

    val session = remember { CaptureSession(context, lifecycleOwner) }
    val previewView = remember { PreviewView(context) }

    fun requiredPermissions(): Array<String> =
        if (mode == CaptureMode.VIDEO) arrayOf(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO) else arrayOf(Manifest.permission.CAMERA)

    fun hasAllPermissions(): Boolean = requiredPermissions().all {
        ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED
    }

    var denialCount by remember { mutableIntStateOf(0) }
    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { results ->
        if (results.values.all { it }) {
            permissionState = PermissionState.GRANTED
        } else {
            denialCount += 1
            canAskAgain = denialCount < 2
            permissionState = PermissionState.DENIED
        }
    }

    LaunchedEffect(mode) {
        permissionState = if (hasAllPermissions()) PermissionState.GRANTED else PermissionState.UNKNOWN
        Log.d(LOG_TAG, "permission_check mode=$mode result=$permissionState")
    }

    // Returns true if it is safe to navigate away immediately. While a capture is in
    // flight, the coroutine that started it (the shutter/record button's own scope.launch)
    // is the sole owner of that evidence row's next write -- calling cancelCapture here
    // concurrently with that coroutine's eventual finalizeCapture on the SAME row would
    // race two writers against one id. So: if recording, just request a stop and let that
    // owning coroutine finish and navigate away itself; if any other capture is in flight
    // (e.g. a photo mid-shutter), do nothing and wait rather than touching the row.
    suspend fun cleanupActiveCapture(): Boolean {
        if (captureInFlight) {
            if (isRecording) session.stopRecording()
            return false
        }
        activeEvidenceId?.let { viewModel.cancelCapture(it) }
        activeEvidenceId = null
        return true
    }

    BackHandler {
        scope.launch {
            if (cleanupActiveCapture()) onDone()
        }
    }

    DisposableEffect(Unit) {
        onDispose {
            session.unbind()
        }
    }

    LaunchedEffect(mode, quality, permissionState) {
        if (permissionState == PermissionState.GRANTED) {
            session.bind(previewView, mode, quality)
                .onSuccess {
                    Log.d(LOG_TAG, "camera_bind mode=$mode result=success")
                    // A PREVIOUS bind attempt for this same screen (e.g. right after the
                    // permission grant, before the camera subsystem had settled) can have left
                    // the unavailable-camera message on screen -- clear it now the live preview
                    // is actually up, or it lingers forever despite a working feed.
                    if (statusMessageRes == R.string.capture_error_camera_unavailable) statusMessageRes = null
                }
                .onFailure {
                    Log.w(LOG_TAG, "camera_bind mode=$mode result=failed category=${it::class.simpleName}")
                    statusMessageRes = R.string.capture_error_camera_unavailable
                }
        }
    }

    KpCaptureScaffold(title = "$taskId — " + stringResource(taskTitleRes(taskId)), onCancel = { scope.launch { if (cleanupActiveCapture()) onDone() } }) {
        when (permissionState) {
            PermissionState.UNKNOWN -> {
                PermissionRationale(
                    mode = mode,
                    canAskAgain = true,
                    onRequest = { permissionLauncher.launch(requiredPermissions()) },
                    onOpenSettings = {},
                )
            }
            PermissionState.DENIED -> {
                PermissionRationale(
                    mode = mode,
                    canAskAgain = canAskAgain,
                    onRequest = { permissionLauncher.launch(requiredPermissions()) },
                    onOpenSettings = {
                        context.startActivity(
                            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null))
                                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                        )
                    },
                )
            }
            PermissionState.GRANTED -> {
                Column(modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(bottom = 8.dp)) {
                        FilterChip(
                            selected = mode == CaptureMode.PHOTO,
                            onClick = { if (!captureInFlight) mode = CaptureMode.PHOTO },
                            label = { Text(stringResource(R.string.evidence_type_photo)) },
                            modifier = Modifier.testTag("capture_mode_photo"),
                        )
                        FilterChip(
                            selected = mode == CaptureMode.VIDEO,
                            onClick = { if (!captureInFlight) mode = CaptureMode.VIDEO },
                            label = { Text(stringResource(R.string.evidence_type_video)) },
                            modifier = Modifier.testTag("capture_mode_video"),
                        )
                    }

                    if (mode == CaptureMode.VIDEO) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(bottom = 8.dp)) {
                            FilterChip(
                                selected = quality == VideoQualityChoice.SD,
                                onClick = { if (!captureInFlight) quality = VideoQualityChoice.SD },
                                label = { Text(stringResource(R.string.capture_quality_sd)) },
                                modifier = Modifier.testTag("capture_quality_sd"),
                            )
                            FilterChip(
                                selected = quality == VideoQualityChoice.HD,
                                onClick = { if (!captureInFlight) quality = VideoQualityChoice.HD },
                                label = { Text(stringResource(R.string.capture_quality_hd)) },
                                modifier = Modifier.testTag("capture_quality_hd"),
                            )
                        }
                    }

                    if (BuildConfig.P4_TEST_ONLY_CEILING_ENABLED) {
                        Row(modifier = Modifier.padding(bottom = 8.dp)) {
                            Text(
                                stringResource(R.string.p4_test_only_ceiling_label, formatMb(BuildConfig.P4_TEST_ONLY_CEILING_BYTES)),
                                style = MaterialTheme.typography.bodySmall,
                                modifier = Modifier.weight(1f),
                            )
                            Switch(
                                checked = debugCeilingRequested,
                                onCheckedChange = { if (!isRecording) debugCeilingRequested = it },
                                modifier = Modifier.testTag("p4_test_only_ceiling_toggle"),
                            )
                        }
                    }

                    AndroidView(
                        factory = { previewView },
                        modifier = Modifier.fillMaxWidth().weight(1f).clip(RoundedCornerShape(14.dp)).testTag("capture_preview_view"),
                    )

                    if (isRecording) {
                        Text(
                            stringResource(R.string.capture_recording_indicator),
                            color = MaterialTheme.colorScheme.error,
                            style = MaterialTheme.typography.titleMedium,
                            modifier = Modifier.padding(top = 12.dp).testTag("capture_recording_indicator"),
                        )
                        Text(
                            stringResource(R.string.capture_size_used, formatMb(bytesRecorded), formatMb(ceilingBytes)),
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.fillMaxWidth().padding(top = 4.dp).testTag("capture_size_used"),
                        )
                        LinearProgressIndicator(
                            progress = { if (ceilingBytes > 0) (bytesRecorded.toFloat() / ceilingBytes).coerceIn(0f, 1f) else 0f },
                            modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                        )
                        Text(
                            stringResource(R.string.capture_remaining_budget, formatMb(ceilingBytes - bytesRecorded)),
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.fillMaxWidth().testTag("capture_remaining_budget"),
                        )
                        Text(stringResource(R.string.capture_local_size_note), style = MaterialTheme.typography.bodySmall, modifier = Modifier.fillMaxWidth().padding(top = 4.dp))
                    }

                    statusMessageRes?.let {
                        Text(
                            stringResource(it),
                            color = MaterialTheme.colorScheme.error,
                            style = MaterialTheme.typography.bodyMedium,
                            modifier = Modifier.padding(top = 12.dp).testTag("capture_status_message"),
                        )
                    }

                    FilledIconButton(
                        onClick = {
                            scope.launch {
                                statusMessageRes = null
                                if (mode == CaptureMode.PHOTO) {
                                    captureInFlight = true
                                    val success = runPhotoCapture(
                                        viewModel = viewModel,
                                        session = session,
                                        taskId = taskId,
                                        replacesEvidenceId = replacesEvidenceId,
                                        debugCeilingRequested = debugCeilingRequested,
                                        onEvidenceStarted = { activeEvidenceId = it },
                                        onStatus = { statusMessageRes = it },
                                    )
                                    captureInFlight = false
                                    activeEvidenceId = null
                                    // Room's suspend DAO calls inside finalizeCapture() run on Room's own
                                    // transaction executor and the coroutine can resume on that thread
                                    // rather than hopping back to Main (observed on a real device --
                                    // Navigation's popBackStack() enforces a main-thread Lifecycle write
                                    // and crashes otherwise). withContext(Main.immediate) guarantees this
                                    // call lands on the main thread regardless of where we resumed.
                                    if (success) withContext(Dispatchers.Main.immediate) { onDone() }
                                } else if (!isRecording) {
                                    captureInFlight = true
                                    val autoClose = startVideoCapture(
                                        viewModel = viewModel,
                                        session = session,
                                        taskId = taskId,
                                        replacesEvidenceId = replacesEvidenceId,
                                        debugCeilingRequested = debugCeilingRequested,
                                        onEvidenceStarted = { activeEvidenceId = it },
                                        onCeilingKnown = { ceilingBytes = it },
                                        onBytesRecorded = { bytesRecorded = it },
                                        onRecordingStateChanged = { if (it) bytesRecorded = 0L; isRecording = it },
                                        onStatus = { statusMessageRes = it },
                                    )
                                    captureInFlight = false
                                    activeEvidenceId = null
                                    // See the equivalent photo-branch comment above -- same fix, same reason.
                                    if (autoClose) withContext(Dispatchers.Main.immediate) { onDone() }
                                } else {
                                    session.stopRecording()
                                }
                            }
                        },
                        modifier = Modifier.padding(top = 16.dp, bottom = 8.dp).size(76.dp)
                            .testTag(if (mode == CaptureMode.PHOTO) "btn_capture_shutter" else "btn_capture_record"),
                        enabled = !captureInFlight || isRecording,
                        shape = CircleShape,
                        colors = IconButtonDefaults.filledIconButtonColors(containerColor = if (mode == CaptureMode.VIDEO) Color(0xFFFF6B57) else Color(0xFFFBF6EC), contentColor = if (mode == CaptureMode.VIDEO) Color(0xFFFBF6EC) else Color(0xFF4C2C17)),
                    ) {
                        Icon(imageVector = when { mode == CaptureMode.PHOTO -> Icons.Filled.PhotoCamera; isRecording -> Icons.Filled.Stop; else -> Icons.Filled.FiberManualRecord }, contentDescription = when { mode == CaptureMode.PHOTO -> stringResource(R.string.capture_action_take_photo); isRecording -> stringResource(R.string.capture_action_stop_recording); else -> stringResource(R.string.capture_action_start_recording) }, modifier = Modifier.size(32.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun KpCaptureScaffold(title: String, onCancel: () -> Unit, content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = darkColorScheme(primary = Color(0xFFC9A06B), onPrimary = Color(0xFF2A1C0F), background = Color(0xFF17120C), surface = Color(0xFF17120C), onSurface = Color(0xFFFBF6EC), outline = Color(0xFF6B5744), error = Color(0xFFFF6B57))) {
        Surface(color = MaterialTheme.colorScheme.background) {
            Column(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing)) {
                Row(Modifier.fillMaxWidth().heightIn(min = 54.dp).padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = onCancel, modifier = Modifier.testTag("btn_capture_cancel")) { Icon(Icons.Filled.Close, contentDescription = stringResource(R.string.action_cancel)) }
                    Text(title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                }
                Box(Modifier.weight(1f)) { content() }
            }
        }
    }
}

@Composable
private fun PermissionRationale(mode: CaptureMode, canAskAgain: Boolean, onRequest: () -> Unit, onOpenSettings: () -> Unit) {
    Column(modifier = Modifier.fillMaxSize().padding(24.dp)) {
        Text(
            if (mode == CaptureMode.VIDEO) stringResource(R.string.capture_permission_rationale_video) else stringResource(R.string.capture_permission_rationale_photo),
            style = MaterialTheme.typography.bodyLarge,
        )
        if (canAskAgain) {
            Button(
                onClick = onRequest,
                modifier = Modifier.fillMaxWidth().padding(top = 16.dp).defaultMinTapTarget().testTag("capture_permission_grant_button"),
            ) {
                Text(stringResource(R.string.capture_permission_grant_action))
            }
        } else {
            Text(
                stringResource(R.string.capture_permission_denied_permanently),
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.padding(top = 8.dp),
            )
            Button(
                onClick = onOpenSettings,
                modifier = Modifier.fillMaxWidth().padding(top = 16.dp).defaultMinTapTarget().testTag("capture_open_settings_button"),
            ) {
                Text(stringResource(R.string.capture_action_open_settings))
            }
        }
    }
}

/** Returns true if a usable photo was captured and finalized (the caller should navigate
 * back); false if rejected by a budget/space check or if finalize failed (the caller
 * stays on screen so [onStatus]'s message is visible and the user can retry). */
private suspend fun runPhotoCapture(
    viewModel: AppViewModel,
    session: CaptureSession,
    taskId: String,
    replacesEvidenceId: String?,
    debugCeilingRequested: Boolean,
    onEvidenceStarted: (String) -> Unit,
    onStatus: (Int) -> Unit,
): Boolean {
    if (!viewModel.hasEnoughFreeSpace()) {
        onStatus(R.string.capture_error_insufficient_space)
        return false
    }
    val begin = viewModel.beginCapture(taskId, EvidenceType.PHOTO, debugCeilingRequested, replacesEvidenceId)
    return when (begin) {
        is BeginCaptureResult.Rejected -> {
            onStatus(rejectionMessage(begin.reason))
            false
        }
        is BeginCaptureResult.Started -> {
            onEvidenceStarted(begin.evidenceId)
            when (val result = session.takePhotoAwait(begin.stagingFile)) {
                is PhotoResult.Success -> {
                    when (
                        viewModel.finalizeCapture(
                            begin.evidenceId,
                            success = true,
                            widthPx = result.widthPx,
                            heightPx = result.heightPx,
                        )
                    ) {
                        is FinalizeResult.Ready -> true
                        is FinalizeResult.RejectedOverLimit -> {
                            onStatus(R.string.capture_error_over_limit)
                            false
                        }
                        FinalizeResult.Failed -> {
                            onStatus(R.string.capture_error_finalize_failed)
                            false
                        }
                    }
                }
                is PhotoResult.Error -> {
                    viewModel.finalizeCapture(begin.evidenceId, success = false)
                    onStatus(R.string.capture_error_finalize_failed)
                    false
                }
            }
        }
    }
}

/** Returns true only when the recording finished normally (stopped by the user) AND
 * finalized successfully -- the caller should then navigate back. Returns false when
 * rejected up front, when finalize failed, or when the safety ceiling auto-stopped the
 * recording: in that last case the clip IS saved as READY evidence, but the caller stays
 * on screen so the "safety limit reached" message in [onStatus] is actually readable
 * rather than flashing past during an immediate navigation. */
private suspend fun startVideoCapture(
    viewModel: AppViewModel,
    session: CaptureSession,
    taskId: String,
    replacesEvidenceId: String?,
    debugCeilingRequested: Boolean,
    onEvidenceStarted: (String) -> Unit,
    onCeilingKnown: (Long) -> Unit,
    onBytesRecorded: (Long) -> Unit,
    onRecordingStateChanged: (Boolean) -> Unit,
    onStatus: (Int) -> Unit,
): Boolean {
    if (!viewModel.hasEnoughFreeSpace()) {
        onStatus(R.string.capture_error_insufficient_space)
        return false
    }
    val begin = viewModel.beginCapture(taskId, EvidenceType.VIDEO, debugCeilingRequested, replacesEvidenceId)
    return when (begin) {
        is BeginCaptureResult.Rejected -> {
            onStatus(rejectionMessage(begin.reason))
            false
        }
        is BeginCaptureResult.Started -> {
            onEvidenceStarted(begin.evidenceId)
            onCeilingKnown(begin.ceilingBytes)
            onRecordingStateChanged(true)
            var stoppedForCeiling = false
            // Stop at a conservative threshold below the real ceiling, not the ceiling
            // itself -- CameraX reports recorded bytes on periodic status ticks, so the
            // recording always writes a little more after this check fires. See
            // EvidenceRepository.videoStopThresholdBytes for the documented guard band; the
            // real safety guarantee is finalizeCapture()'s fail-closed real-file-size check
            // below, not this early-stop heuristic.
            val stopThreshold = EvidenceRepository.videoStopThresholdBytes(begin.ceilingBytes)
            val result = session.recordVideoAwait(begin.stagingFile, recordAudio = true) { bytes ->
                onBytesRecorded(bytes)
                if (!stoppedForCeiling && bytes >= stopThreshold) {
                    stoppedForCeiling = true
                    onStatus(R.string.capture_safety_limit_reached)
                    session.stopRecording()
                }
            }
            onRecordingStateChanged(false)
            when (result) {
                is VideoResult.Success -> {
                    when (
                        viewModel.finalizeCapture(
                            begin.evidenceId,
                            success = true,
                            widthPx = result.widthPx,
                            heightPx = result.heightPx,
                            durationMillis = result.durationMillis,
                        )
                    ) {
                        is FinalizeResult.Ready -> !stoppedForCeiling
                        is FinalizeResult.RejectedOverLimit -> {
                            onStatus(R.string.capture_error_over_limit)
                            false
                        }
                        FinalizeResult.Failed -> {
                            onStatus(R.string.capture_error_finalize_failed)
                            false
                        }
                    }
                }
                is VideoResult.Error -> {
                    viewModel.finalizeCapture(begin.evidenceId, success = false)
                    onStatus(R.string.capture_error_finalize_failed)
                    false
                }
            }
        }
    }
}

private fun rejectionMessage(reason: CaptureRejectionReason): Int = when (reason) {
    CaptureRejectionReason.INSUFFICIENT_FREE_SPACE -> R.string.capture_error_insufficient_space
    CaptureRejectionReason.TASK_BUDGET_EXHAUSTED -> R.string.add_evidence_error_task_budget
    CaptureRejectionReason.TOTAL_BUDGET_EXHAUSTED -> R.string.add_evidence_error_total_budget
}
