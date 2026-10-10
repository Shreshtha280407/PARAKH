package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.data.DeclarationCardCatalog
import `in`.kaushalpramaan.app.data.DeclarationCardUi
import `in`.kaushalpramaan.app.data.DeclarationSection
import `in`.kaushalpramaan.app.ui.components.KpScaffold
import `in`.kaushalpramaan.app.ui.components.defaultMinTapTarget
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp

@Composable
fun DeclarationScreen(viewModel: AppViewModel, onBack: () -> Unit, onSeeMatch: () -> Unit) {
    val uiState by viewModel.uiState.collectAsState()
    val cards = remember { DeclarationCardCatalog.allCards() }
    val tools = remember { DeclarationCardCatalog.allTools() }

    KpScaffold(
        title = stringResource(R.string.declaration_title),
        language = uiState.language,
        onLanguageChange = viewModel::setLanguage,
        onBack = onBack,
    ) { modifier ->
        LazyColumn(modifier = modifier.fillMaxSize().padding(horizontal = 16.dp).testTag("declaration_lazy_column")) {
            item {
                Text(
                    stringResource(R.string.declaration_instructions),
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(vertical = 16.dp),
                )
            }

            for (section in listOf(
                DeclarationSection.PRACTICAL,
                DeclarationSection.SAFETY,
                DeclarationSection.TEAMWORK,
                DeclarationSection.PLANNING,
            )) {
                item {
                    Text(
                        stringResource(section.titleRes),
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(top = 16.dp, bottom = 8.dp),
                    )
                }
                items(cards.filter { it.section == section }, key = { it.id }) { card ->
                    DeclarationAnswerRow(
                        card = card,
                        currentAnswer = uiState.declaration.answers[card.id],
                        onAnswer = { answer -> viewModel.setAnswer(card.id, answer) },
                    )
                }
            }

            item {
                Text(
                    stringResource(R.string.declaration_section_tools_grid),
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(top = 24.dp, bottom = 8.dp),
                )
            }
            items(tools, key = { it.id }) { tool ->
                DeclarationAnswerRow(
                    card = tool,
                    currentAnswer = uiState.declaration.answers[tool.id],
                    onAnswer = { answer -> viewModel.setAnswer(tool.id, answer) },
                )
            }

            item {
                HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))
                Text(stringResource(R.string.declaration_years_label), style = MaterialTheme.typography.titleMedium)
                Text(
                    "${uiState.declaration.yearsOfExperience}",
                    style = MaterialTheme.typography.headlineSmall,
                    modifier = Modifier.padding(vertical = 4.dp),
                )
                Slider(
                    value = uiState.declaration.yearsOfExperience.toFloat(),
                    onValueChange = { viewModel.setYearsOfExperience(it.toInt()) },
                    valueRange = 0f..30f,
                    steps = 29,
                    modifier = Modifier.defaultMinTapTarget(),
                )

                Text(
                    stringResource(R.string.declaration_free_text_label),
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(top = 16.dp),
                )
                OutlinedTextField(
                    value = uiState.declaration.freeText,
                    onValueChange = viewModel::setFreeText,
                    placeholder = { Text(stringResource(R.string.declaration_free_text_hint)) },
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                    minLines = 3,
                )

                Button(
                    onClick = onSeeMatch,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 24.dp)
                        .defaultMinTapTarget()
                        .testTag("btn_see_match"),
                ) {
                    Text(stringResource(R.string.action_see_match))
                }
            }
        }
    }
}

@Composable
private fun DeclarationAnswerRow(card: DeclarationCardUi, currentAnswer: String?, onAnswer: (String) -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(stringResource(card.labelRes), style = MaterialTheme.typography.bodyLarge)
            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                AnswerChip(card.id, stringResource(R.string.answer_often), "often", currentAnswer, onAnswer)
                AnswerChip(card.id, stringResource(R.string.answer_sometimes), "sometimes", currentAnswer, onAnswer)
                AnswerChip(card.id, stringResource(R.string.answer_never), "never", currentAnswer, onAnswer)
            }
        }
    }
}

@Composable
private fun AnswerChip(itemId: String, label: String, value: String, currentAnswer: String?, onAnswer: (String) -> Unit) {
    FilterChip(
        selected = currentAnswer == value,
        onClick = { onAnswer(value) },
        label = { Text(label) },
        modifier = Modifier.defaultMinTapTarget().testTag("answer_${itemId}_$value"),
    )
}
