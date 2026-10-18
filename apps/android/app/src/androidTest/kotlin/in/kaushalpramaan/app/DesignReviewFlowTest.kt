package `in`.kaushalpramaan.app

import android.graphics.Bitmap
import android.view.WindowManager
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import org.junit.Rule
import org.junit.Test

/** Review artifacts contain only this isolated QA app's synthetic onboarding data.
 * Production FLAG_SECURE is unchanged. The window flag is cleared only inside
 * this instrumentation run, after asserting the separate validation package. */
@OptIn(ExperimentalTestApi::class)
class DesignReviewFlowTest {
    @get:Rule(order = 0) val clear = ClearP4DraftBeforeTest()
    @get:Rule(order = 1) val compose = createAndroidComposeRule<MainActivity>()

    private fun snapshot(name: String) {
        check(compose.activity.packageName.endsWith(".p8validation"))
        compose.runOnIdle { compose.activity.window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE) }
        compose.waitForIdle()
        UiDevice.getInstance(InstrumentationRegistry.getInstrumentation()).waitForIdle()
        val image = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        checkNotNull(image)
        val directory = compose.activity.filesDir.resolve("ui-review").apply { mkdirs() }
        directory.resolve("$name.png").outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 100, it) }
        image.recycle()
    }

    @Test fun suppliedDesignScreensRemainNavigableAndActionsStayVisible() {
        compose.waitUntilExactlyOneExists(hasTestTag("lang_option_en"), 15_000)
        snapshot("01-language")
        compose.tapTag("lang_option_en"); compose.tapTag("btn_continue")
        snapshot("02-consent")
        compose.tapTag("consent_checkbox"); compose.tapTag("btn_continue")
        snapshot("03-candidate-details")
        compose.onNodeWithTag("reg_name").performTextInput("Design Review Candidate")
        compose.onNodeWithTag("reg_phone").performTextInput("9876543210")
        compose.onNodeWithTag("reg_pin").performTextInput("1847")
        compose.onNodeWithTag("reg_pin_confirm").performTextInput("1847")
        compose.tapTag("btn_register")
        compose.waitUntilExactlyOneExists(hasTestTag("declaration_lazy_column"), 15_000)
        compose.onNodeWithTag("btn_see_match").assertIsDisplayed()
        snapshot("04-declaration")
        compose.tapTag("btn_see_match")
        compose.onNodeWithTag("btn_view_tasks").assertIsDisplayed()
        snapshot("05-match-result")
        compose.tapTag("btn_view_tasks")
        compose.onNodeWithTag("btn_preview").assertIsDisplayed()
        snapshot("06-practice-tasks")
        compose.tapInLazyColumn("task_list_lazy_column", "task_card_T3")
        compose.onNodeWithTag("btn_add_evidence").assertIsDisplayed()
        compose.onNodeWithTag("btn_back_to_tasks").assertIsDisplayed()
        snapshot("07-task-detail")
        compose.tapTag("btn_back_to_tasks"); compose.tapTag("btn_preview")
        compose.onNodeWithTag("btn_submit").assertIsDisplayed().assertIsNotEnabled()
        snapshot("11-review-and-seal")
    }
}
