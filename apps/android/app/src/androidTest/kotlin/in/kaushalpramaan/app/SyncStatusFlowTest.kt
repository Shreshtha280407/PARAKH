package `in`.kaushalpramaan.app

import android.graphics.Bitmap
import android.view.WindowManager
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.platform.app.InstrumentationRegistry
import androidx.work.WorkInfo
import androidx.work.WorkManager
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.data.draft.*
import `in`.kaushalpramaan.app.data.sync.SyncWorker
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.MediaType.Companion.toMediaType
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TestRule
import org.junit.runner.Description
import org.junit.runners.model.Statement

/** Synthetic JPEG fixture through real encrypted Room, seal/sign/vault,
 * WorkManager and a real local FastAPI/Postgres backend behind a fault proxy.
 * No production candidates, credentials or media are used. */
@OptIn(ExperimentalTestApi::class)
class SyncStatusFlowTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val db get() = AppDatabase.getInstance(context)
    private val http = OkHttpClient()
    @get:Rule(order = 0) val isolated = TestRule { base, _: Description -> object : Statement() {
        override fun evaluate() {
            check(context.packageName.endsWith(".p8validation"))
            check(BuildConfig.P6_TEST_ONLY_DEFAULT_SYNC_BASE_URL == "http://127.0.0.1:18008")
            base.evaluate()
        }
    } }
    @get:Rule(order = 1) val clear = ClearP4DraftBeforeTest()
    @get:Rule(order = 2) val ui = createAndroidComposeRule<MainActivity>()
    private fun control(mode: String, reset: Boolean = false) {
        val body = "{\"mode\":\"$mode\",\"reset\":$reset}".toRequestBody("application/json".toMediaType())
        http.newCall(Request.Builder().url("http://127.0.0.1:18008/_test/sync-mode").post(body).build()).execute().use { assertEquals(200, it.code) }
    }
    private fun attempts(): Int = http.newCall(Request.Builder().url("http://127.0.0.1:18008/_test/sync-stats").build()).execute().use {
        JSONObject(it.body!!.string()).getInt("upload_attempts")
    }
    private fun waitForStableInternet() {
        val network = context.getSystemService(android.net.ConnectivityManager::class.java)
        val deadline = System.currentTimeMillis() + 30_000
        var consecutive = 0
        while (System.currentTimeMillis() < deadline) {
            val caps = network.getNetworkCapabilities(network.activeNetwork)
            consecutive = if (caps?.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_VALIDATED) == true) consecutive + 1 else 0
            if (consecutive >= 10) return
            Thread.sleep(100)
        }
        error("The phone needs validated internet for the real worker's online sync test")
    }
    private fun waitTag(tag: String) = ui.waitUntilExactlyOneExists(hasTestTag(tag), 30_000)
    private fun snapshot(name: String) {
        ui.runOnIdle { ui.activity.window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE) }
        ui.waitForIdle()
        val bitmap = checkNotNull(InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot())
        val directory = context.filesDir.resolve("sync-review").apply { mkdirs() }
        directory.resolve("$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }
    private fun dismissNotice() {
        if (ui.onAllNodesWithTag("sync_notice_dismiss").fetchSemanticsNodes().isNotEmpty()) ui.tapTag("sync_notice_dismiss")
    }
    @Test fun sealStartsOnceFailureWaitsForManualRetryThenServerConfirmsSuccess() {
        control("fail", reset = true)
        ui.completeIntake("en", phone = "9000000000")
        ui.onNodeWithText("EN ⇄ हि").performClick()
        ui.onNodeWithText("हि ⇄ EN").assertIsDisplayed().performClick()
        ui.onNodeWithText("EN ⇄ हि").assertIsDisplayed()
        ui.tapTag("btn_see_match"); ui.tapTag("btn_view_tasks")
        val vm = ViewModelProvider(ui.activity)[AppViewModel::class.java]
        ui.waitUntil(15_000) { vm.uiState.value.assessmentDraftId != null }
        ui.runOnIdle { ui.activity.window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE) }
        runBlocking {
            val capture = vm.beginCapture("T1", EvidenceType.PHOTO, false, null) as BeginCaptureResult.Started
            val image = Bitmap.createBitmap(640, 480, Bitmap.Config.ARGB_8888)
            image.eraseColor(android.graphics.Color.rgb(107, 63, 35))
            capture.stagingFile.outputStream().use { image.compress(Bitmap.CompressFormat.JPEG, 95, it) }
            image.recycle()
            assertTrue(vm.finalizeCapture(capture.evidenceId, true, 640, 480) is FinalizeResult.Ready)
        }
        ui.tapTag("btn_preview")
        ui.onNodeWithTag("sync_status_card").assertIsDisplayed()
        assertTrue(ui.onNodeWithTag("sync_status_card").fetchSemanticsNode().boundsInRoot.top <
            ui.onNodeWithTag("final_review_task_T1").fetchSemanticsNode().boundsInRoot.top)
        ui.tapTag("btn_optimize_evidence")
        ui.waitUntil(30_000) { runBlocking { db.assessmentDraftDao().getActiveOnce()?.sealState == SealState.FINAL_REVIEW_READY } }
        waitForStableInternet()
        ui.tapTag("attestation_checkbox"); ui.tapTag("btn_submit")
        waitTag("submitted_title")
        // No Retry/Sync button was pressed: the first real request is automatic.
        waitTag("sync_status_notice")
        val assessment = runBlocking { db.assessmentDraftDao().getActiveOnce()!! }
        val name = SyncWorker.uniqueWorkName(assessment.id, assessment.revisionId!!)
        ui.waitUntil(30_000) { WorkManager.getInstance(context).getWorkInfosForUniqueWork(name).get().any { it.state == WorkInfo.State.FAILED } }
        assertEquals(1, attempts())
        snapshot("01-sync-failed-popup")
        dismissNotice()
        ui.onNodeWithTag("btn_sync_now").assertIsDisplayed().assertIsEnabled()
        snapshot("02-sync-failed-card")
        Thread.sleep(3_000)
        assertEquals("A failed sync must not retry automatically", 1, attempts())

        // Relaunching the Activity must not create another automatic attempt.
        ui.activityRule.scenario.recreate()
        waitTag("unlock_pin")
        ui.runOnIdle { ui.activity.window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE) }
        ui.onNodeWithTag("unlock_pin").performTextInput("1234"); ui.tapTag("btn_unlock")
        ui.waitUntil(30_000) {
            ui.onAllNodesWithTag("task_list_lazy_column").fetchSemanticsNodes().isNotEmpty() ||
                ui.onAllNodesWithTag("sync_status_card").fetchSemanticsNodes().isNotEmpty()
        }
        // Android can restore the sealed destination rather than route through
        // the task list after a configuration change. Both are valid paths.
        if (ui.onAllNodesWithTag("task_list_lazy_column").fetchSemanticsNodes().isNotEmpty()) ui.tapTag("btn_preview")
        if (ui.onAllNodesWithText("View sealed evidence").fetchSemanticsNodes().isNotEmpty()) ui.onNodeWithText("View sealed evidence").performClick()
        dismissNotice()
        ui.onNodeWithTag("sync_status_card").assertIsDisplayed()
        // Each manually requested failed attempt gets its own failure popup.
        waitForStableInternet()
        ui.tapTag("btn_sync_now")
        waitTag("sync_status_notice")
        assertEquals(2, attempts())
        dismissNotice()
        control("success")
        Thread.sleep(3_000)
        assertEquals("Server availability/recomposition must not retry without a tap", 2, attempts())

        waitForStableInternet()
        ui.tapTag("btn_sync_now")
        ui.waitUntil(30_000) { ui.onAllNodesWithTag("sync_progress_active").fetchSemanticsNodes().isNotEmpty() }
        snapshot("03-sync-running")
        ui.waitUntil(60_000) { runBlocking { db.assessmentDraftDao().getActiveOnce()?.syncedAtMillis != null } }
        waitTag("sync_status_notice")
        snapshot("04-sync-completed-popup")
        ui.tapTag("sync_notice_confirm")
        ui.onNodeWithTag("sync_overall_synced").assertIsDisplayed()
        ui.onAllNodesWithTag("btn_sync_now").assertCountEquals(0)
        snapshot("05-sync-completed-card")
        val done = runBlocking { db.assessmentDraftDao().getActiveOnce()!! }
        http.newCall(Request.Builder().url("http://127.0.0.1:18008/public/assessments/${done.serverAssessmentId}").build()).execute().use {
            assertEquals(200, it.code)
            assertEquals("submitted", JSONObject(it.body!!.string()).getString("status"))
        }
        InstrumentationRegistry.getInstrumentation().sendStatus(2, android.os.Bundle().apply {
            putLong("submitted_server_assessment_id", done.serverAssessmentId!!)
            putInt("upload_attempts_including_failure_and_manual_retry", attempts())
        })
    }
}
