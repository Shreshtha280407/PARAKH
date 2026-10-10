package `in`.kaushalpramaan.app.ui.components

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppLanguage
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Language
import androidx.compose.material.icons.filled.WifiOff
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp

/** Shared top bar for every P-3 screen: optional back button, a language
 * toggle (EN<->HI, available from any screen per spec), and a small offline
 * indicator so it's always visible that no network is needed. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun KpScaffold(
    title: String,
    language: AppLanguage,
    onLanguageChange: (AppLanguage) -> Unit,
    onBack: (() -> Unit)? = null,
    content: @Composable (Modifier) -> Unit,
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(title) },
                navigationIcon = {
                    if (onBack != null) {
                        IconButton(onClick = onBack) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = stringResource(R.string.content_desc_back))
                        }
                    }
                },
                actions = {
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(end = 4.dp)) {
                        Icon(
                            Icons.Filled.WifiOff,
                            contentDescription = stringResource(R.string.offline_badge),
                            modifier = Modifier.padding(end = 8.dp),
                        )
                        IconButton(onClick = {
                            onLanguageChange(if (language == AppLanguage.ENGLISH) AppLanguage.HINDI else AppLanguage.ENGLISH)
                        }) {
                            Icon(Icons.Filled.Language, contentDescription = stringResource(R.string.content_desc_language_switch))
                        }
                    }
                },
            )
        },
    ) { padding ->
        content(Modifier.padding(padding))
    }
}
