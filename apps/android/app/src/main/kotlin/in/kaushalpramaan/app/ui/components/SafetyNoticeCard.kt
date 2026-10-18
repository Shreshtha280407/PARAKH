package `in`.kaushalpramaan.app.ui.components

import `in`.kaushalpramaan.app.R
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Warning
import `in`.kaushalpramaan.app.ui.components.KpCard as Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp

/** The single global safety notice shown before task execution (TaskListScreen,
 * before the worker can open any individual task) and reinforced on every
 * individual task (TaskDetailScreen) -- one shared composable so the two
 * places can never drift to different wording. Carries testTag "safety_notice"
 * for the instrumented tests that assert it is always displayed. */
@Composable
fun SafetyNoticeCard(modifier: Modifier = Modifier) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
        modifier = modifier.fillMaxWidth().testTag("safety_notice"),
    ) {
        Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.Warning, contentDescription = null)
            Text(
                stringResource(R.string.safety_notice_text),
                modifier = Modifier.padding(start = 8.dp),
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}
