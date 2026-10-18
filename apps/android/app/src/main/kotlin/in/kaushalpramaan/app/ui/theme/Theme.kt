package `in`.kaushalpramaan.app.ui.theme

import `in`.kaushalpramaan.app.R
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

val Brand = Color(0xFF6B3F23)
val BrandDark = Color(0xFF4C2C17)
val BrandLight = Color(0xFF8B5A36)
val Paper = Color(0xFFFBF6EC)
val Cream = Color(0xFFF4E8D3)
val Sand = Color(0xFFC9A06B)
val Line = Color(0xFFE6D7BC)
val Ink = Color(0xFF3A2718)
val DisplayFont = FontFamily(Font(R.font.fraunces, FontWeight.Medium), Font(R.font.fraunces, FontWeight.SemiBold), Font(R.font.fraunces, FontWeight.Bold))
private val BodyFont = FontFamily(Font(R.font.noto_sans), Font(R.font.noto_sans, FontWeight.Medium), Font(R.font.noto_sans, FontWeight.SemiBold), Font(R.font.noto_sans, FontWeight.Bold))
val MonoFont = FontFamily(Font(R.font.jetbrains_mono))
private val Colors = lightColorScheme(
    primary = Brand, onPrimary = Color.White, primaryContainer = Cream, onPrimaryContainer = BrandDark,
    secondary = BrandLight, onSecondary = Color.White, secondaryContainer = Cream, onSecondaryContainer = Ink,
    tertiary = Color(0xFF2F7D5B), onTertiary = Color.White, tertiaryContainer = Color(0xFFE6EFE8), onTertiaryContainer = Color(0xFF2F7D5B),
    error = Color(0xFFB23A2E), errorContainer = Color(0xFFF6E7DF), onErrorContainer = Ink,
    background = Paper, onBackground = Ink, surface = Paper, onSurface = Ink,
    surfaceVariant = Cream, onSurfaceVariant = BrandLight, outline = Line, outlineVariant = Line,
    surfaceContainerLowest = Color.White, surfaceContainerLow = Color.White, surfaceContainer = Color.White,
    surfaceContainerHigh = Cream, surfaceContainerHighest = Cream,
)
private val Type = Typography(
    headlineLarge = TextStyle(fontFamily = DisplayFont, fontWeight = FontWeight.SemiBold, fontSize = 30.sp, lineHeight = 38.sp),
    headlineMedium = TextStyle(fontFamily = DisplayFont, fontWeight = FontWeight.SemiBold, fontSize = 24.sp, lineHeight = 32.sp),
    headlineSmall = TextStyle(fontFamily = DisplayFont, fontWeight = FontWeight.SemiBold, fontSize = 22.sp, lineHeight = 30.sp),
    titleLarge = TextStyle(fontFamily = DisplayFont, fontWeight = FontWeight.SemiBold, fontSize = 20.sp, lineHeight = 28.sp),
    titleMedium = TextStyle(fontFamily = BodyFont, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, lineHeight = 21.sp),
    titleSmall = TextStyle(fontFamily = BodyFont, fontWeight = FontWeight.SemiBold, fontSize = 13.sp, lineHeight = 20.sp),
    bodyLarge = TextStyle(fontFamily = BodyFont, fontSize = 14.sp, lineHeight = 23.sp),
    bodyMedium = TextStyle(fontFamily = BodyFont, fontSize = 13.sp, lineHeight = 21.sp),
    bodySmall = TextStyle(fontFamily = BodyFont, fontSize = 12.sp, lineHeight = 19.sp),
    labelLarge = TextStyle(fontFamily = BodyFont, fontWeight = FontWeight.Bold, fontSize = 14.sp, lineHeight = 20.sp),
    labelMedium = TextStyle(fontFamily = BodyFont, fontWeight = FontWeight.SemiBold, fontSize = 12.sp, lineHeight = 18.sp),
    labelSmall = TextStyle(fontFamily = BodyFont, fontWeight = FontWeight.SemiBold, fontSize = 11.sp, lineHeight = 16.sp),
)

@Composable
fun KaushalPramaanTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = Colors, typography = Type,
        shapes = Shapes(extraSmall = RoundedCornerShape(6.dp), small = RoundedCornerShape(9.dp), medium = RoundedCornerShape(12.dp), large = RoundedCornerShape(14.dp), extraLarge = RoundedCornerShape(16.dp)), content = content)
}
