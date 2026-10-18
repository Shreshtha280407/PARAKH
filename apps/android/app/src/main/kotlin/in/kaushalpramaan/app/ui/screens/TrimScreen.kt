package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.ui.components.KpScaffold
import `in`.kaushalpramaan.app.ui.components.KpBottomBar
import `in`.kaushalpramaan.app.ui.components.KpButton
import `in`.kaushalpramaan.app.ui.components.formatDuration
import android.net.Uri
import android.widget.MediaController
import android.widget.VideoView
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import kotlinx.coroutines.launch
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun TrimScreen(viewModel: AppViewModel, evidenceId: String, onDone: () -> Unit, onCancel: () -> Unit) {
    val state by viewModel.uiState.collectAsState()
    val evidence = state.evidenceByTask.values.flatten().firstOrNull { it.id == evidenceId }
    val scope = rememberCoroutineScope()
    val duration = evidence?.durationMillis ?: 0L
    var range by remember(evidenceId, duration) { mutableStateOf(0f..duration.toFloat()) }
    var trimming by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf(false) }
    var player by remember { mutableStateOf<VideoView?>(null) }
    KpScaffold(title = stringResource(R.string.action_trim), language = state.language, onLanguageChange = viewModel::setLanguage, onBack = { if (!trimming) onCancel() }, bottomBar = { KpBottomBar {
        KpButton(onClick = { scope.launch { trimming = true; error = false; try { val success = viewModel.trimVideo(evidenceId, range.start.toLong(), range.endInclusive.toLong()); withContext(Dispatchers.Main.immediate) { if (success) onDone() else error = true } } catch (_: Exception) { error = true } finally { trimming = false } } }, enabled = evidence != null && duration > 0 && !trimming && range.endInclusive - range.start > 500f, modifier = Modifier.fillMaxWidth().testTag("btn_confirm_trim")) { if (trimming) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp); Text(stringResource(R.string.action_trim)) }
    } }) { modifier ->
        Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(18.dp)) {
            if (evidence == null || duration <= 0) { Text(stringResource(R.string.trim_error), color = MaterialTheme.colorScheme.error); return@Column }
            val file = remember(evidence.relativePath, evidence.finalRelativePath) { viewModel.evidenceFile(evidence) }
            AndroidView(factory = { context -> VideoView(context).apply { setVideoURI(Uri.fromFile(file)); setMediaController(MediaController(context).also { it.setAnchorView(this) }); setOnPreparedListener { seekTo(range.start.toInt()) }; setOnErrorListener { _, _, _ -> error = true; true }; player = this } }, onReset = null, onRelease = { it.stopPlayback(); player = null }, modifier = Modifier.fillMaxWidth().aspectRatio(3f / 4f).testTag("trim_video_preview"))
            Text(stringResource(R.string.trim_range_label, formatDuration(range.start.toLong()), formatDuration(range.endInclusive.toLong())), style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 18.dp))
            RangeSlider(value = range, onValueChange = { range = it; player?.pause(); player?.seekTo(it.start.toInt()) }, valueRange = 0f..duration.toFloat(), enabled = !trimming, modifier = Modifier.fillMaxWidth().padding(top = 12.dp).testTag("trim_range_slider"))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text("0:00", style = MaterialTheme.typography.bodySmall); Text(formatDuration(duration / 2), style = MaterialTheme.typography.bodySmall); Text(formatDuration(duration), style = MaterialTheme.typography.bodySmall) }
            if (error) Text(stringResource(R.string.trim_error), color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 12.dp))
        }
    }
}
