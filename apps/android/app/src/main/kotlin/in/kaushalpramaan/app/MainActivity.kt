package `in`.kaushalpramaan.app

import `in`.kaushalpramaan.app.data.AppLanguage
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.ui.AppNavGraph
import `in`.kaushalpramaan.app.ui.theme.KaushalPramaanTheme
import android.content.res.Configuration
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.LocalActivityResultRegistryOwner
import androidx.activity.compose.LocalOnBackPressedDispatcherOwner
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext

class MainActivity : ComponentActivity() {

    private val viewModel: AppViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            val uiState by viewModel.uiState.collectAsState()
            LocalizedApp(language = uiState.language) {
                KaushalPramaanTheme {
                    Surface(modifier = Modifier.fillMaxSize()) {
                        Box(modifier = Modifier.fillMaxSize()) {
                            AppNavGraph(viewModel = viewModel)
                        }
                    }
                }
            }
        }
    }
}

/** Overrides LocalContext/LocalConfiguration for the subtree so every
 * stringResource() call resolves against [language] immediately, without an
 * Activity recreate() -- the standard Compose-only approach for in-app
 * language switching (P-3 requirement: "language can be changed before
 * starting"). */
@Composable
fun LocalizedApp(language: AppLanguage, content: @Composable () -> Unit) {
    val baseContext = LocalContext.current
    // Source the base Configuration from LocalConfiguration.current, not
    // context.resources.configuration directly -- the latter is a lint error
    // (LocalContextConfigurationRead): it isn't a Compose-tracked read, so a
    // config change elsewhere would not invalidate it. LocalConfiguration.current
    // is tracked; remember() below is additionally keyed on `language` itself,
    // which is what actually drives a locale switch here.
    val currentConfiguration = LocalConfiguration.current
    val localizedContext = remember(language, baseContext, currentConfiguration) {
        val locale = language.toLocale()
        val config = Configuration(currentConfiguration)
        config.setLocale(locale)
        baseContext.createConfigurationContext(config)
    }
    // Context.createConfigurationContext() returns a standalone Context that does NOT wrap
    // the original Activity in its ContextWrapper chain. androidx.activity's
    // LocalOnBackPressedDispatcherOwner/LocalActivityResultRegistryOwner resolve their
    // default value by unwrapping LocalContext.current looking for the Activity -- so
    // overriding LocalContext here (needed for the locale switch) would otherwise silently
    // break BackHandler and rememberLauncherForActivityResult for every screen beneath this
    // point (both throw IllegalStateException when the owner can't be found). Resolving
    // both owners from the REAL, pre-override ambient context here and re-providing them
    // explicitly keeps them correct regardless of the LocalContext swap.
    val backDispatcherOwner = LocalOnBackPressedDispatcherOwner.current
    val activityResultRegistryOwner = LocalActivityResultRegistryOwner.current
    val providedLocals = buildList {
        add(LocalContext provides localizedContext)
        add(LocalConfiguration provides localizedContext.resources.configuration)
        backDispatcherOwner?.let { add(LocalOnBackPressedDispatcherOwner provides it) }
        activityResultRegistryOwner?.let { add(LocalActivityResultRegistryOwner provides it) }
    }.toTypedArray()
    CompositionLocalProvider(*providedLocals) {
        content()
    }
}
