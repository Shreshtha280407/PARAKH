package `in`.kaushalpramaan.app.ui.components

import android.content.Context
import android.speech.tts.TextToSpeech
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import java.util.Locale

/**
 * Thin wrapper around Android's local, on-device TextToSpeech engine for the
 * consent audio-prompt button. Must degrade gracefully with no network and
 * no TTS engine/voice data installed -- this is a pure best-effort affordance,
 * never required to complete the flow (see ConsentScreen's "continue" button,
 * which is never gated on audio having played).
 */
class TtsController(private val context: Context) {
    private var engine: TextToSpeech? = null
    var isAvailable by mutableStateOf(false)
        private set

    fun init() {
        engine = TextToSpeech(context) { status ->
            isAvailable = status == TextToSpeech.SUCCESS
        }
    }

    fun speak(text: String, locale: Locale) {
        val tts = engine ?: return
        if (!isAvailable) return
        val result = tts.setLanguage(locale)
        if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
            isAvailable = false
            return
        }
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "kp-consent")
    }

    fun shutdown() {
        engine?.stop()
        engine?.shutdown()
        engine = null
    }
}

@Composable
fun rememberTtsController(): TtsController {
    val context = LocalContext.current
    val controller = remember { TtsController(context) }
    DisposableEffect(Unit) {
        controller.init()
        onDispose { controller.shutdown() }
    }
    return controller
}
