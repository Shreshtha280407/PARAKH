package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.ui.components.KpBottomBar
import `in`.kaushalpramaan.app.ui.components.KpOutlinedButton
import `in`.kaushalpramaan.app.ui.components.KpScaffold
import `in`.kaushalpramaan.app.ui.components.AssessmentSyncStatus
import `in`.kaushalpramaan.app.ui.theme.MonoFont
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp

@Composable
fun SubmittedScreen(viewModel: AppViewModel, onViewPreviewAgain: () -> Unit) {
    val uiState by viewModel.uiState.collectAsState()
    KpScaffold(title = stringResource(R.string.submitted_title), language = uiState.language, onLanguageChange = viewModel::setLanguage,
        bottomBar = { KpBottomBar { KpOutlinedButton(onClick = onViewPreviewAgain, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.action_view_preview_again)) } } }) { modifier ->
        Column(modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(18.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            AssessmentSyncStatus(viewModel, modifier = Modifier.padding(bottom = 28.dp))
            Icon(if (uiState.syncedAtMillis != null) Icons.Filled.CheckCircle else Icons.Filled.Lock, contentDescription = null,
                tint = if (uiState.syncedAtMillis != null) MaterialTheme.colorScheme.tertiary else MaterialTheme.colorScheme.primary, modifier = Modifier.size(60.dp))
            Text(stringResource(R.string.submitted_title), style = MaterialTheme.typography.headlineSmall, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 22.dp).testTag("submitted_title"))
            Text(stringResource(R.string.submitted_body), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 12.dp).testTag("sealed_status_message"))
            uiState.registration?.let { Text(stringResource(R.string.submitted_worker_id, it.workerId), style = MaterialTheme.typography.bodySmall, fontFamily = MonoFont, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 24.dp)) }
        }
    }
}
