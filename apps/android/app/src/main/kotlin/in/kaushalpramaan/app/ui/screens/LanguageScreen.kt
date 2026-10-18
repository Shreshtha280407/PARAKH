package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppLanguage
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.ui.components.KpBottomBar
import `in`.kaushalpramaan.app.ui.components.KpButton
import `in`.kaushalpramaan.app.ui.theme.*
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat
import android.app.Activity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun LanguageScreen(viewModel: AppViewModel, onContinue: () -> Unit) {
    val state by viewModel.uiState.collectAsState()
    val view = LocalView.current
    DisposableEffect(view) {
        val controller = (view.context as? Activity)?.window?.let { WindowCompat.getInsetsController(it, view) }
        val previousAppearance = controller?.isAppearanceLightStatusBars
        controller?.isAppearanceLightStatusBars = true
        onDispose { if (previousAppearance != null) controller?.isAppearanceLightStatusBars = previousAppearance }
    }
    Scaffold(containerColor = Paper, bottomBar = { KpBottomBar { KpButton(onClick = onContinue, modifier = Modifier.fillMaxWidth().testTag("btn_continue")) { Text(stringResource(R.string.action_continue)) } } }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(horizontal = 28.dp).padding(top = 48.dp, bottom = 24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Image(painterResource(R.drawable.parakh_emblem), contentDescription = "PARAKH", modifier = Modifier.size(110.dp))
            Text("PARAKH", style = MaterialTheme.typography.headlineLarge, color = BrandDark, modifier = Modifier.padding(top = 14.dp))
            Text("Prior-skill Assessment & Recognition\nthrough AI-driven Knowledge", style = MaterialTheme.typography.labelSmall, color = BrandLight, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 6.dp))
            Column(Modifier.fillMaxWidth().padding(top = 44.dp)) {
                Text(stringResource(R.string.language_title), style = MaterialTheme.typography.headlineSmall, color = BrandDark)
                Text(stringResource(R.string.language_subtitle), style = MaterialTheme.typography.bodyMedium, color = BrandLight, modifier = Modifier.padding(top = 6.dp, bottom = 16.dp))
                LanguageOption(stringResource(R.string.language_english), state.language == AppLanguage.ENGLISH, { viewModel.setLanguage(AppLanguage.ENGLISH) }, "lang_option_en")
                LanguageOption(stringResource(R.string.language_hindi), state.language == AppLanguage.HINDI, { viewModel.setLanguage(AppLanguage.HINDI) }, "lang_option_hi")
            }
        }
    }
}

@Composable
private fun LanguageOption(label: String, selected: Boolean, onSelect: () -> Unit, tag: String) {
    Surface(color = if (selected) Cream else androidx.compose.ui.graphics.Color.White, border = BorderStroke(1.dp, if (selected) Brand else Line), shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp).selectable(selected = selected, onClick = onSelect, role = Role.RadioButton).testTag(tag)) {
        Row(Modifier.padding(horizontal = 8.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            RadioButton(selected = selected, onClick = null)
            Text(label, style = MaterialTheme.typography.titleMedium, fontSize = 16.sp, modifier = Modifier.padding(start = 8.dp))
        }
    }
}
