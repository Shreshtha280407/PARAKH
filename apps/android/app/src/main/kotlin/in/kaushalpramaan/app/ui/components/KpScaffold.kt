package `in`.kaushalpramaan.app.ui.components

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppLanguage
import `in`.kaushalpramaan.app.ui.theme.BrandDark
import `in`.kaushalpramaan.app.ui.theme.Paper
import `in`.kaushalpramaan.app.ui.theme.DisplayFont
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.font.FontWeight

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun KpScaffold(title: String, language: AppLanguage, onLanguageChange: (AppLanguage) -> Unit, onBack: (() -> Unit)? = null, bottomBar: @Composable () -> Unit = {}, content: @Composable (Modifier) -> Unit) {
    val connectionStatus = rememberConnectionStatus()
    Scaffold(containerColor = Paper, bottomBar = bottomBar, topBar = {
        TopAppBar(title = {
            if (title.equals("PARAKH", ignoreCase = true)) {
                Text("Parakh", fontFamily = DisplayFont, fontWeight = FontWeight.Bold, fontSize = 25.sp, letterSpacing = .5.sp)
            } else Text(title, style = MaterialTheme.typography.titleMedium, fontSize = 15.sp, maxLines = 2)
        }, expandedHeight = 58.dp,
            colors = TopAppBarDefaults.topAppBarColors(containerColor = BrandDark, titleContentColor = Paper, navigationIconContentColor = Paper, actionIconContentColor = Paper),
            navigationIcon = { if (onBack != null) IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = stringResource(R.string.content_desc_back)) } },
            actions = { val languageDescription = stringResource(R.string.content_desc_language_switch)
                Row(verticalAlignment = Alignment.CenterVertically) {
                ConnectionIndicator(connectionStatus)
                TextButton(onClick = { onLanguageChange(if (language == AppLanguage.ENGLISH) AppLanguage.HINDI else AppLanguage.ENGLISH) }, modifier = Modifier.padding(horizontal = 4.dp).semantics { contentDescription = languageDescription }) {
                    Text(if (language == AppLanguage.HINDI) "हि ⇄ EN" else "EN ⇄ हि", color = Paper, style = MaterialTheme.typography.labelSmall, modifier = Modifier.background(Paper.copy(alpha = .16f), RoundedCornerShape(50)).padding(horizontal = 9.dp, vertical = 5.dp))
                }
            } })
    }) { padding -> content(Modifier.padding(padding)) }
}
