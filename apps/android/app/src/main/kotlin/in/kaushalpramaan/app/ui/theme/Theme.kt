package `in`.kaushalpramaan.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val KpBlue = Color(0xFF1E3A8A)
private val KpAmber = Color(0xFFF59E0B)
private val KpGreen = Color(0xFF15803D)
private val KpRed = Color(0xFFB91C1C)

private val LightColors = lightColorScheme(
    primary = KpBlue,
    secondary = KpAmber,
    tertiary = KpGreen,
    error = KpRed,
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF93C5FD),
    secondary = KpAmber,
    tertiary = Color(0xFF86EFAC),
    error = Color(0xFFFCA5A5),
)

@Composable
fun KaushalPramaanTheme(
    useDarkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val colors = if (useDarkTheme) DarkColors else LightColors
    MaterialTheme(
        colorScheme = colors,
        typography = MaterialTheme.typography,
        content = content,
    )
}
