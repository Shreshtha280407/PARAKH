package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.ui.components.KpScaffold
import `in`.kaushalpramaan.app.ui.components.defaultMinTapTarget
import `in`.kaushalpramaan.app.ui.components.formatDuration
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RangeSlider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

/**
 * P5's minimal offline video trim screen (spec part D.5): start/end time only, no
 * bitrate/resolution/quality control anywhere on this screen. Trimming goes through
 * [AppViewModel.trimVideo] -> [in.kaushalpramaan.app.data.seal.SealOrchestrator.trimVideo] --
 * the same validation/optimiser/budget-ledger pipeline as any other capture; the existing
 * clip stays valid in the worker's eyes until the trimmed output is genuinely ready.
 */
@Composable
fun TrimScreen(viewModel: AppViewModel, evidenceId: String, onDone: () -> Unit, onCancel: () -> Unit) {
    val uiState by viewModel.uiState.collectAsState()
    val evidence = uiState.evidenceByTask.values.flatten().firstOrNull { it.id == evidenceId }
    val scope = rememberCoroutineScope()
    var range by remember { mutableStateOf<ClosedFloatingPointRange<Float>?>(null) }
    var trimming by remember { mutableStateOf(false) }
    var errorShown by remember { mutableStateOf(false) }

    val durationMs = evidence?.durationMillis ?: 0L
    LaunchedEffect(durationMs) {
        if (range == null && durationMs > 0) range = 0f..durationMs.toFloat()
    }

    KpScaffold(
        title = stringResource(R.string.action_trim),
        language = uiState.language,
        onLanguageChange = viewModel::setLanguage,
        onBack = onCancel,
    ) { modifier ->
        Column(modifier = modifier.fillMaxSize().padding(16.dp)) {
            if (evidence == null || durationMs <= 0) {
                Text(stringResource(R.string.loading))
                return@KpScaffold
            }
            val current = range ?: 0f..durationMs.toFloat()
            Text(
                stringResource(R.string.trim_range_label, formatDuration(current.start.toLong()), formatDuration(current.endInclusive.toLong())),
                style = MaterialTheme.typography.titleMedium,
            )
            RangeSlider(
                value = current,
                onValueChange = { range = it },
                valueRange = 0f..durationMs.toFloat(),
                modifier = Modifier.fillMaxWidth().padding(top = 16.dp).testTag("trim_range_slider"),
            )
            if (errorShown) {
                Text(
                    stringResource(R.string.trim_error),
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }
            Button(
                onClick = {
                    scope.launch {
                        trimming = true
                        errorShown = false
                        val success = viewModel.trimVideo(evidenceId, current.start.toLong(), current.endInclusive.toLong())
                        trimming = false
                        if (success) onDone() else errorShown = true
                    }
                },
                enabled = !trimming && (current.endInclusive - current.start) > 500f,
                modifier = Modifier.fillMaxWidth().padding(top = 24.dp).defaultMinTapTarget().testTag("btn_confirm_trim"),
            ) {
                if (trimming) CircularProgressIndicator(modifier = Modifier.padding(end = 8.dp))
                Text(stringResource(R.string.action_trim))
            }
        }
    }
}
