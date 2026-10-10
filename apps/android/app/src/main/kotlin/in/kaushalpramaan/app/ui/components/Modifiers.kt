package `in`.kaushalpramaan.app.ui.components

import androidx.compose.foundation.layout.sizeIn
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/** Accessibility: Material/WCAG recommend a minimum 48dp tap target. Applied
 * to every primary action and selectable row in the P-3 flow. */
fun Modifier.defaultMinTapTarget(): Modifier = this.sizeIn(minWidth = 48.dp, minHeight = 48.dp)
