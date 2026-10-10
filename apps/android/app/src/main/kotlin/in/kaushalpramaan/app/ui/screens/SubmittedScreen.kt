package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.ui.components.KpScaffold
import `in`.kaushalpramaan.app.ui.components.defaultMinTapTarget
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
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
fun SubmittedScreen(viewModel: AppViewModel, onViewPreviewAgain: () -> Unit) {
    val uiState by viewModel.uiState.collectAsState()

    KpScaffold(
        title = stringResource(R.string.submitted_title),
        language = uiState.language,
        onLanguageChange = viewModel::setLanguage,
    ) { modifier ->
        Column(
            modifier = modifier.fillMaxSize().padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Icon(
                Icons.Filled.CheckCircle,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.tertiary,
                modifier = Modifier.padding(top = 32.dp),
            )
            Text(
                stringResource(R.string.submitted_title),
                style = MaterialTheme.typography.headlineSmall,
                modifier = Modifier.padding(top = 16.dp).testTag("submitted_title"),
            )
            Text(
                stringResource(R.string.submitted_body),
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.padding(top = 16.dp),
            )
            uiState.registration?.let {
                Text(
                    stringResource(R.string.submitted_worker_id, it.workerId),
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(top = 16.dp),
                )
            }
            Button(
                onClick = onViewPreviewAgain,
                modifier = Modifier.fillMaxWidth().padding(top = 32.dp).defaultMinTapTarget(),
            ) {
                Text(stringResource(R.string.action_view_preview_again))
            }
        }
    }
}
