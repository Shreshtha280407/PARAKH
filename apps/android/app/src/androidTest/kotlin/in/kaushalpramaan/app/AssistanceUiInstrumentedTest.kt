package `in`.kaushalpramaan.app

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import `in`.kaushalpramaan.app.data.assistance.AssistanceRecord
import `in`.kaushalpramaan.app.ui.components.AssistanceCard
import `in`.kaushalpramaan.app.ui.theme.KaushalPramaanTheme
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Real production Compose guidance; no AppViewModel or production DB is opened. */
@RunWith(AndroidJUnit4::class)
class AssistanceUiInstrumentedTest {
    @get:Rule val compose = createComposeRule()
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private fun record(status: String, result: String? = null, frozen: String? = null) = AssistanceRecord(
        "photo-1", "assessment-1", "T1", 1, "ui-test", "synthetic.jpg", "a".repeat(64), null,
        status, "queued", result, frozen, null)
    private fun photoFixture() = InstrumentationRegistry.getInstrumentation().context.assets
        .open("assistance-v1-photo.json").bufferedReader().use { it.readText() }

    @Test fun queued_is_progress_not_a_bad_capture_and_can_be_cancelled() {
        var cancelled = false
        compose.setContent { KaushalPramaanTheme { AssistanceCard(record("QUEUED"), false,
            onCancel = { cancelled = true }) } }
        compose.onNodeWithText(context.getString(R.string.assistance_queued)).assertIsDisplayed()
        compose.onNodeWithText(context.getString(R.string.assistance_dark)).assertDoesNotExist()
        compose.onNodeWithText(context.getString(R.string.assistance_advisory)).assertIsDisplayed()
        compose.onNodeWithText(context.getString(R.string.assistance_cancel)).performClick()
        assertTrue(cancelled)
    }

    @Test fun unavailable_displays_continue_guidance_and_safe_retry() {
        var retried = false
        compose.setContent { KaushalPramaanTheme { AssistanceCard(record("UNAVAILABLE"), false,
            onRetry = { retried = true }) } }
        compose.onNodeWithText(context.getString(R.string.assistance_unavailable)).assertIsDisplayed()
        compose.onNodeWithText(context.getString(R.string.assistance_dark)).assertDoesNotExist()
        compose.onNodeWithTag("btn_retry_assistance").performClick()
        assertTrue(retried)
    }

    @Test fun actual_warning_is_advisory_and_never_introduces_an_acceptance_control() {
        compose.setContent { KaushalPramaanTheme { AssistanceCard(record("COMPLETED", photoFixture()), false) } }
        compose.onNodeWithText(context.getString(R.string.assistance_dark)).assertIsDisplayed()
        compose.onNodeWithText(context.getString(R.string.assistance_advisory)).assertIsDisplayed()
        compose.onNodeWithTag("btn_retry_assistance").assertDoesNotExist()
    }

    @Test fun sealed_snapshot_wins_over_late_live_state_and_has_no_edit_controls() {
        compose.setContent { KaushalPramaanTheme { AssistanceCard(record("RUNNING", frozen = photoFixture()), true,
            onRetry = { fail("sealed retry") }, onCancel = { fail("sealed cancel") }) } }
        compose.onNodeWithText(context.getString(R.string.assistance_dark)).assertIsDisplayed()
        compose.onNodeWithText(context.getString(R.string.assistance_sealed_snapshot)).assertIsDisplayed()
        compose.onNodeWithText(context.getString(R.string.assistance_running)).assertDoesNotExist()
        compose.onNodeWithText(context.getString(R.string.assistance_cancel)).assertDoesNotExist()
        compose.onNodeWithTag("btn_retry_assistance").assertDoesNotExist()
    }
}
