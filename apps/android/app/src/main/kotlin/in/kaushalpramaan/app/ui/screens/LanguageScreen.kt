package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppLanguage
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.ui.components.defaultMinTapTarget
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp

@Composable
fun LanguageScreen(viewModel: AppViewModel, onContinue: () -> Unit) {
    val uiState by viewModel.uiState.collectAsState()

    Scaffold { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(24.dp),
            verticalArrangement = Arrangement.Center,
        ) {
            Text(stringResource(R.string.language_title), style = MaterialTheme.typography.headlineMedium)
            Text(
                stringResource(R.string.language_subtitle),
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(top = 8.dp, bottom = 24.dp),
            )

            LanguageOption(
                label = stringResource(R.string.language_english),
                selected = uiState.language == AppLanguage.ENGLISH,
                onSelect = { viewModel.setLanguage(AppLanguage.ENGLISH) },
                tag = "lang_option_en",
            )
            LanguageOption(
                label = stringResource(R.string.language_hindi),
                selected = uiState.language == AppLanguage.HINDI,
                onSelect = { viewModel.setLanguage(AppLanguage.HINDI) },
                tag = "lang_option_hi",
            )

            Button(
                onClick = onContinue,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 32.dp)
                    .defaultMinTapTarget()
                    .testTag("btn_continue"),
            ) {
                Text(stringResource(R.string.action_continue))
            }
        }
    }
}

@Composable
private fun LanguageOption(label: String, selected: Boolean, onSelect: () -> Unit, tag: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp)
            .selectable(selected = selected, onClick = onSelect, role = Role.RadioButton)
            .defaultMinTapTarget()
            .testTag(tag),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        RadioButton(selected = selected, onClick = onSelect)
        Text(label, style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(start = 8.dp))
    }
}
