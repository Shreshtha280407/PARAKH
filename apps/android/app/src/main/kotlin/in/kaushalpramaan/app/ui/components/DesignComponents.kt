package `in`.kaushalpramaan.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import `in`.kaushalpramaan.app.ui.theme.Line

@Composable
fun KpButton(onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, content: @Composable RowScope.() -> Unit) {
    Button(onClick = onClick, modifier = modifier.heightIn(min = 50.dp), enabled = enabled, shape = RoundedCornerShape(10.dp), contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp), content = content)
}

@Composable
fun KpOutlinedButton(onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, content: @Composable RowScope.() -> Unit) {
    OutlinedButton(onClick = onClick, modifier = modifier.heightIn(min = 46.dp), enabled = enabled, shape = RoundedCornerShape(10.dp), border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary), content = content)
}

@Composable
fun KpCard(modifier: Modifier = Modifier, colors: CardColors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer), content: @Composable ColumnScope.() -> Unit) {
    Card(modifier = modifier, colors = colors, border = BorderStroke(1.dp, Line), shape = RoundedCornerShape(12.dp), content = content)
}

@Composable
fun KpFilterChip(selected: Boolean, onClick: () -> Unit, label: @Composable () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    FilterChip(selected = selected, onClick = onClick, label = label, modifier = modifier, enabled = enabled,
        shape = RoundedCornerShape(50), colors = FilterChipDefaults.filterChipColors(containerColor = MaterialTheme.colorScheme.surfaceContainer, selectedContainerColor = MaterialTheme.colorScheme.primary, selectedLabelColor = MaterialTheme.colorScheme.onPrimary),
        border = FilterChipDefaults.filterChipBorder(enabled = enabled, selected = selected, borderColor = Line, selectedBorderColor = MaterialTheme.colorScheme.primary))
}

@Composable
fun KpBottomBar(content: @Composable ColumnScope.() -> Unit) {
    Surface(color = MaterialTheme.colorScheme.background) {
        Column { HorizontalDivider(); Column(Modifier.fillMaxWidth().imePadding().padding(horizontal = 18.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp), content = content) }
    }
}
