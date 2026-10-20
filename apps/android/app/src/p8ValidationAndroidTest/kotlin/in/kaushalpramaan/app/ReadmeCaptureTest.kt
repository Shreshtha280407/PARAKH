package `in`.kaushalpramaan.app

import android.graphics.Bitmap
import android.os.SystemClock
import android.view.WindowManager
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Rule
import org.junit.Test

/** A reproducible visual capture driver, compiled only into the separate QA app. */
@OptIn(ExperimentalTestApi::class)
class ReadmeCaptureTest {
    @get:Rule(order = 0) val clear = ClearP4DraftBeforeTest()
    @get:Rule(order = 1) val ui = createAndroidComposeRule<MainActivity>()

    private fun shot(name: String) {
        check(ui.activity.packageName.endsWith(".p8validation"))
        ui.runOnIdle { ui.activity.window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE) }
        ui.waitForIdle()
        SystemClock.sleep(2200)
        val image = checkNotNull(InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot())
        val directory = ui.activity.filesDir.resolve("readme-captures").apply { mkdirs() }
        directory.resolve("$name.png").outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 100, it) }
        image.recycle()
    }

    @Test fun captureWorkerJourney() {
        ui.waitUntilExactlyOneExists(hasTestTag("lang_option_en"), 15_000)
        shot("app-language")
        ui.tapTag("lang_option_hi"); shot("app-hindi")
        ui.tapTag("lang_option_en"); ui.tapTag("btn_continue")
        shot("app-consent")
        ui.tapTag("consent_checkbox"); ui.tapTag("btn_continue")
        shot("app-registration")
        ui.onNodeWithTag("reg_name").performTextInput("README Sample Candidate")
        ui.onNodeWithTag("reg_phone").performTextInput("9876543210")
        ui.onNodeWithTag("reg_pin").performTextInput("1847")
        ui.onNodeWithTag("reg_pin_confirm").performTextInput("1847")
        ui.tapTag("btn_register")
        ui.waitUntilExactlyOneExists(hasTestTag("declaration_lazy_column"), 15_000)
        shot("app-declaration")
        ui.answerAllDeclarationItems("often")
        shot("app-match")
        ui.tapTag("btn_view_tasks")
        shot("app-tasks")
        ui.tapInLazyColumn("task_list_lazy_column", "task_card_T3")
        shot("app-task-detail")
        ui.tapTag("btn_back_to_tasks"); ui.tapTag("btn_preview")
        shot("app-review")
    }
}
