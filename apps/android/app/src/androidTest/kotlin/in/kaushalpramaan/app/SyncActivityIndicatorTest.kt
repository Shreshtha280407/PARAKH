package `in`.kaushalpramaan.app

import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.graphics.toPixelMap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import `in`.kaushalpramaan.app.ui.components.SyncPhase
import `in`.kaushalpramaan.app.ui.components.SyncPresentation
import `in`.kaushalpramaan.app.ui.components.SyncStatusContent
import `in`.kaushalpramaan.app.ui.theme.KaushalPramaanTheme
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

/** Runs in the separate QA package; never opens or clears the worker's draft. */
class SyncActivityIndicatorTest {
    @get:Rule val ui = createComposeRule()

    @Test fun spinnerKeepsMovingUntilFailureAndRestartsOnRetry() {
        check(InstrumentationRegistry.getInstrumentation().targetContext.packageName.endsWith(".p8validation"))
        val phase = mutableStateOf(SyncPhase.UPLOADING)
        ui.mainClock.autoAdvance = false
        ui.setContent {
            KaushalPramaanTheme {
                SyncStatusContent(SyncPresentation(phase.value, uploadedBytes = 400, totalBytes = 1000),
                    onRetry = { phase.value = SyncPhase.QUEUED })
            }
        }
        ui.mainClock.advanceTimeBy(100)
        val spinner = ui.onNodeWithTag("sync_activity_indicator")
        spinner.assertIsDisplayed()
        fun pixels(): List<Int> {
            val bitmap = spinner.captureToImage().toPixelMap()
            return List(bitmap.width * bitmap.height) { i -> bitmap[i % bitmap.width, i / bitmap.width].hashCode() }
        }
        val before = pixels()
        ui.mainClock.advanceTimeBy(250)
        val after = pixels()
        assertNotEquals("Spinner pixels must move even when device animation scale is zero", before, after)
        ui.onNodeWithTag("btn_sync_now").assertIsNotEnabled()
        ui.runOnUiThread { phase.value = SyncPhase.FAILED }
        ui.mainClock.advanceTimeBy(32)
        spinner.assertDoesNotExist()
        ui.onNodeWithTag("btn_sync_now").assertIsEnabled().performClick()
        ui.mainClock.advanceTimeBy(100)
        spinner.assertIsDisplayed()
        ui.runOnUiThread { phase.value = SyncPhase.VERIFYING }
        ui.mainClock.advanceTimeBy(100)
        spinner.assertIsDisplayed()
        ui.runOnUiThread { phase.value = SyncPhase.SUBMITTED }
        ui.mainClock.advanceTimeBy(32)
        spinner.assertDoesNotExist()
    }
}
