package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.ui.components.KpScaffold
import `in`.kaushalpramaan.app.ui.components.defaultMinTapTarget
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import kotlin.math.roundToInt

@Composable
fun MatchResultScreen(viewModel: AppViewModel, onBack: () -> Unit, onViewTasks: () -> Unit) {
    val uiState by viewModel.uiState.collectAsState()
    val output = uiState.matchOutput

    KpScaffold(
        title = stringResource(R.string.match_title),
        language = uiState.language,
        onLanguageChange = viewModel::setLanguage,
        onBack = onBack,
    ) { modifier ->
        if (output == null) {
            Column(modifier = modifier.fillMaxSize().padding(24.dp)) {
                CircularProgressIndicator()
                Text(stringResource(R.string.loading), modifier = Modifier.padding(top = 8.dp))
            }
            return@KpScaffold
        }

        Column(modifier = modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp)) {
            val resultLabelRes = when (output.matchResult) {
                "appropriate_match" -> R.string.match_result_appropriate
                "partial_match" -> R.string.match_result_partial
                else -> R.string.match_result_not_appropriate
            }
            val resultColor = when (output.matchResult) {
                "appropriate_match" -> MaterialTheme.colorScheme.tertiary
                "partial_match" -> MaterialTheme.colorScheme.secondary
                else -> MaterialTheme.colorScheme.error
            }

            Card(
                colors = CardDefaults.cardColors(containerColor = resultColor.copy(alpha = 0.15f)),
                modifier = Modifier.fillMaxWidth().testTag("match_result_card"),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(stringResource(resultLabelRes), style = MaterialTheme.typography.headlineSmall)
                    Text(
                        stringResource(R.string.match_coverage_label, (output.overallCoverage * 100).roundToInt()),
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
            }

            Text(
                stringResource(R.string.match_disclaimer),
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(top = 16.dp),
            )

            Text(
                stringResource(R.string.match_because_title),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(top = 24.dp, bottom = 8.dp),
            )
            for (line in output.because) {
                Text("• $line", style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(vertical = 2.dp))
            }

            Text(
                stringResource(R.string.match_gaps_title),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(top = 24.dp, bottom = 8.dp),
            )
            if (output.gapNos.isEmpty()) {
                Text(stringResource(R.string.match_no_gaps), style = MaterialTheme.typography.bodyMedium)
            } else {
                for (nos in output.gapNos) {
                    Text("• $nos", style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(vertical = 2.dp))
                }
            }

            Button(
                onClick = onViewTasks,
                modifier = Modifier.fillMaxWidth().padding(top = 32.dp).defaultMinTapTarget().testTag("btn_view_tasks"),
            ) {
                Text(stringResource(R.string.action_view_tasks))
            }
        }
    }
}
