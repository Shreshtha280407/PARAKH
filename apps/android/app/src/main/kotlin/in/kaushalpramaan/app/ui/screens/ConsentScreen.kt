package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.ui.components.KpBottomBar
import `in`.kaushalpramaan.app.ui.components.KpScaffold
import `in`.kaushalpramaan.app.ui.components.defaultMinTapTarget
import `in`.kaushalpramaan.app.ui.components.rememberTtsController
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import `in`.kaushalpramaan.app.ui.components.KpButton as Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import `in`.kaushalpramaan.app.ui.components.KpOutlinedButton as OutlinedButton
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
fun ConsentScreen(viewModel: AppViewModel, onBack: () -> Unit, onContinue: () -> Unit) {
    val uiState by viewModel.uiState.collectAsState()
    val tts = rememberTtsController()
    val consentBody = stringResource(R.string.consent_body)

    KpScaffold(
        title = stringResource(R.string.consent_title),
        language = uiState.language,
        onLanguageChange = viewModel::setLanguage,
        onBack = onBack,
        bottomBar = { KpBottomBar {
            Button(
                onClick = onContinue,
                enabled = uiState.consentAcknowledged,
                modifier = Modifier
                    .fillMaxWidth()

                    .defaultMinTapTarget()
                    .testTag("btn_continue"),
            ) {
                Text(stringResource(R.string.action_continue))
            }
        } },
    ) { modifier ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(18.dp),
        ) {
            Text(stringResource(R.string.consent_title), style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(bottom = 16.dp).testTag("consent_heading"))
            `in`.kaushalpramaan.app.ui.components.KpCard { Text(consentBody, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(18.dp)) }

            OutlinedButton(
                onClick = { tts.speak(consentBody, uiState.language.toLocale()) },
                enabled = tts.isAvailable,
                modifier = Modifier
                    .padding(top = 16.dp)
                    .defaultMinTapTarget(),
            ) {
                Icon(Icons.AutoMirrored.Filled.VolumeUp, contentDescription = null, modifier = Modifier.padding(end = 8.dp))
                Text(stringResource(R.string.consent_play_audio))
            }
            if (!tts.isAvailable) {
                Text(
                    stringResource(R.string.consent_audio_unavailable),
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }

            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 24.dp)
                    .defaultMinTapTarget(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Checkbox(
                    checked = uiState.consentAcknowledged,
                    onCheckedChange = viewModel::setConsentAcknowledged,
                    modifier = Modifier.testTag("consent_checkbox"),
                )
                Text(stringResource(R.string.consent_checkbox), modifier = Modifier.padding(start = 8.dp))
            }

            if (!uiState.consentAcknowledged) {
                Text(
                    stringResource(R.string.consent_continue_disabled_hint),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }


        }
    }
}
