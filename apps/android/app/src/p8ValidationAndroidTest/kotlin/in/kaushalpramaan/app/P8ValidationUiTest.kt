package `in`.kaushalpramaan.app

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.test.espresso.Espresso.pressBack
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import `in`.kaushalpramaan.app.data.draft.AppDatabase
import `in`.kaushalpramaan.app.data.draft.EvidenceDraftEntity
import `in`.kaushalpramaan.app.data.draft.SealState
import kotlinx.coroutines.runBlocking
import java.util.regex.Pattern
import java.io.File
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TestRule
import org.junit.runner.RunWith
import org.junit.runner.Description
import org.junit.runners.model.Statement

/** Explicit opt-in only: compiled with -Pp8Validation=true, never in the normal
 * test APK. Drives production navigation/CameraX/preview/seal controls, using the
 * real persistent app DB and OS WorkManager. No clearing rule, fake analyzer,
 * repository writes, imported media, or ViewModel shortcuts. Run phases in order.
 * Captures require a human to position a privacy-safe scene before installation. */
@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
class P8ValidationUiTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val args get() = InstrumentationRegistry.getArguments()
    private val db get() = AppDatabase.getInstance(instrumentation.targetContext)

    @get:Rule(order = 0) val isolatedPackage = TestRule { base, _: Description ->
        object : Statement() {
            override fun evaluate() {
                check(instrumentation.targetContext.packageName == "in.kaushalpramaan.app.p8validation") {
                    "Refusing to drive a non-validation package"
                }
                base.evaluate()
            }
        }
    }
    @get:Rule(order = 1) val ui = createAndroidComposeRule<MainActivity>()

    @Test fun production_ui_phase() {
        if (args.getString("p8Phase") != "intake") {
            waitFor {
                ui.onAllNodesWithTag("task_list_lazy_column").fetchSemanticsNodes().isNotEmpty() ||
                    ui.onAllNodesWithTag("unlock_pin").fetchSemanticsNodes().isNotEmpty()
            }
            if (ui.onAllNodesWithTag("unlock_pin").fetchSemanticsNodes().isNotEmpty()) {
                ui.onNodeWithTag("unlock_pin").performTextInput(args.getString("p8Pin") ?: "1234")
                ui.tapTag("btn_unlock")
                waitTag("task_list_lazy_column")
            }
        }
        when (val phase = args.getString("p8Phase")) {
            "intake" -> {
                assertNull(runBlocking { db.assessmentDraftDao().getActiveOnce() })
                ui.completeIntake("en", phone = "9000000000")
                ui.answerAllDeclarationItems("often")
                ui.tapTag("btn_view_tasks")
                waitTag("task_list_lazy_column")
                waitFor { runBlocking { db.assessmentDraftDao().getActiveOnce() != null } }
            }
            "photo-retake-delete" -> photoRetakeDelete()
            "video" -> video()
            "retry" -> {
                val task = args.getString("p8Task") ?: "T2"
                openTask(task)
                val item = taskItems(task).last()
                val old = runBlocking { db.assistanceDao().get(item.id) }!!
                openRow(ui.onAllNodesWithTag("evidence_row").onLast())
                waitTag("btn_retry_assistance")
                ui.tapTag("btn_retry_assistance")
                waitFor(180_000) {
                    runBlocking { db.assistanceDao().get(item.id)?.let {
                        it.generation != old.generation && it.status in setOf("COMPLETED", "PARTIAL")
                    } == true }
                }
                assertEquals(old.inputSha256, runBlocking { db.assistanceDao().get(item.id) }!!.inputSha256)
                ui.onNodeWithTag("assistance_summary").scrollToIfPossible().assertIsDisplayed()
            }
            "inspect" -> {
                val task = args.getString("p8Task") ?: "T2"
                openTask(task)
                val item = taskItems(task).last()
                waitFor(120_000) {
                    runBlocking { db.assistanceDao().get(item.id)?.status in setOf("COMPLETED", "PARTIAL") }
                }
                openRow(ui.onAllNodesWithTag("evidence_row").onLast())
                waitTag("evidence_preview_size")
                ui.onNodeWithTag("assistance_summary").scrollToIfPossible().assertIsDisplayed()
                assertEquals(item.id, runBlocking { db.assistanceDao().get(item.id) }!!.evidenceId)
            }
            "seal" -> seal()
            "sealed-preview" -> {
                waitTag("task_list_lazy_column")
                ui.tapTag("btn_preview")
                waitTag("sealed_status_message")
                assertEquals(SealState.READY_TO_SYNC, runBlocking { db.assessmentDraftDao().getActiveOnce() }!!.sealState)
                ui.onNodeWithTag("sync_status_card").scrollToIfPossible().assertIsDisplayed()
            }
            "check-updates" -> {
                waitTag("task_list_lazy_column")
                ui.tapInLazyColumn("task_list_lazy_column", "btn_check_for_updates")
                waitFor(60_000) { runBlocking { (db.assessmentDraftDao().getActiveOnce()?.currentRevisionNumber ?: 0) >= 2 } }
                val id = runBlocking { db.assessmentDraftDao().getActiveOnce() }!!.id
                assertTrue(runBlocking { db.taskDraftDao().getOne(id, "T1") }!!.locked)
                assertFalse(runBlocking { db.taskDraftDao().getOne(id, "T2") }!!.locked)
            }
            "synced" -> {
                waitFor(180_000) { runBlocking { db.assessmentDraftDao().getActiveOnce()?.syncedAtMillis != null } }
                ui.tapTag("btn_preview")
                waitTag("sync_status_card")
                ui.onNodeWithTag("sync_status_card").scrollToIfPossible().assertIsDisplayed()
                ui.onNodeWithTag("sync_overall_synced").scrollToIfPossible().assertIsDisplayed()
            }
            else -> error("Specify p8Phase: intake, photo-retake-delete, video, inspect, seal, synced, check-updates; got $phase")
        }
        // Let the new NavHost destination finish its enter transition before
        // ActivityScenario closes the host; merely finding its first text node
        // can precede the destination's lifecycle update on the next frame.
        ui.mainClock.advanceTimeBy(1_000)
        ui.waitForIdle()
        instrumentation.sendStatus(2, Bundle().apply { putString("p8_phase", args.getString("p8Phase")) })
        // Optional controlled interruption window: host reads the QA observer's
        // state file then stops ONLY this UID while its real worker is RUNNING.
        // Such a deliberately killed invocation is recorded as interrupted,
        // never counted as a passed JUnit run.
        val hold = args.getString("p8HoldMs")?.toLong() ?: 0L
        require(hold in 0..60_000)
        if (hold > 0) Thread.sleep(hold)
    }

    private fun photoRetakeDelete() {
        openTask("T1")
        // A failed harness attempt may already have finalized its first QA
        // photo. Resume through real retake/delete controls instead of resetting
        // durable data or assuming that restarting instrumentation erases it.
        if (taskItems("T1").isEmpty()) {
            ui.tapTag("btn_add_evidence")
            allowCapturePermissions()
            capturePhoto()
        }
        val original = taskItems("T1").single()
        openFirstPreview()
        ui.onNodeWithTag("assistance_summary").scrollToIfPossible().assertIsDisplayed()
        ui.tapTag("btn_retake_evidence")
        capturePhoto()
        val replacement = taskItems("T1").single()
        assertNotEquals(original.id, replacement.id)
        assertNull(runBlocking { db.evidenceDraftDao().getById(original.id) })
        assertNull(runBlocking { db.assistanceDao().get(original.id) })
        openFirstPreview()
        ui.tapTag("btn_delete_evidence")
        ui.tapTag("btn_confirm_delete_evidence")
        waitTag("btn_add_evidence")
        waitFor { taskItems("T1").isEmpty() }
        assertNull(runBlocking { db.assistanceDao().get(replacement.id) })
        ui.tapTag("btn_add_evidence")
        capturePhoto()
        val retained = taskItems("T1").single()
        waitFor(60_000) { runBlocking { db.assistanceDao().get(retained.id)?.status in setOf("COMPLETED", "PARTIAL") } }
        openFirstPreview()
        ui.onNodeWithTag("assistance_summary").scrollToIfPossible().assertIsDisplayed()
    }

    private fun video() {
        val task = args.getString("p8Task") ?: "T2"
        val seconds = args.getString("p8VideoSeconds")?.toLong() ?: 30L
        require(seconds in 2..60)
        openTask(task)
        ui.tapTag("btn_add_evidence")
        allowCapturePermissions()
        waitTag("capture_mode_video")
        ui.tapTag("capture_mode_video")
        allowCapturePermissions(video = true)
        ui.tapTag("capture_quality_sd")
        ui.tapTag("btn_capture_record")
        waitTag("capture_recording_indicator")
        // Check the visible live label, not merely the final Room/file size.
        // This catches a frozen/zero meter while CameraX is still recording.
        Thread.sleep(seconds * 500)
        val firstLiveLabel = ui.onNodeWithTag("capture_size_used").fetchSemanticsNode().config[SemanticsProperties.Text].joinToString { it.text }
        Thread.sleep(seconds * 500)
        ui.onNodeWithTag("capture_size_used").assertIsDisplayed()
        val secondLiveLabel = ui.onNodeWithTag("capture_size_used").fetchSemanticsNode().config[SemanticsProperties.Text].joinToString { it.text }
        assertNotEquals("The visible size meter must advance during recording", firstLiveLabel, secondLiveLabel)
        instrumentation.sendStatus(2, Bundle().apply {
            putString("live_size_mid_recording", firstLiveLabel)
            putString("live_size_before_stop", secondLiveLabel)
        })
        ui.tapTag("btn_capture_record")
        waitTag("btn_add_evidence", 30_000)
        val item = taskItems(task).last()
        assertTrue((item.durationMillis ?: 0) >= 1_000)
        val storedFile = `in`.kaushalpramaan.app.data.draft.EvidenceFileManager(instrumentation.targetContext).resolveRelativePath(item.relativePath)
        assertTrue(storedFile.isFile)
        assertEquals("Saved evidence meter must equal actual bytes on disk", storedFile.length(), item.byteSize)
        instrumentation.sendStatus(2, Bundle().apply {
            putLong("actual_recorded_file_bytes", storedFile.length())
            putLong("persisted_recorded_bytes", item.byteSize)
            putLong("recorded_duration_ms", item.durationMillis ?: 0L)
        })
        // Navigation away while the real background decoder runs is a product
        // path assertion, independent of whether the observation reports warnings.
        pressBack()
        waitTag("task_list_lazy_column")
        ui.tapTag("btn_preview")
        waitTag("btn_optimize_evidence")
        ui.onAllNodesWithTag("assistance_summary").onLast().scrollToIfPossible().assertIsDisplayed()
    }

    private fun seal() {
        waitTag("task_list_lazy_column")
        ui.tapTag("btn_preview")
        if (runBlocking { db.assessmentDraftDao().getActiveOnce()?.sealState } != SealState.FINAL_REVIEW_READY) {
            waitTag("btn_optimize_evidence")
            ui.tapTag("btn_optimize_evidence")
        }
        waitFor(180_000) { runBlocking { db.assessmentDraftDao().getActiveOnce()?.sealState == SealState.FINAL_REVIEW_READY } }
        ui.onNodeWithTag("attestation_checkbox").scrollToIfPossible().assertIsEnabled().performClick()
        ui.onNodeWithTag("btn_submit").scrollToIfPossible().assertIsEnabled().performClick()
        waitTag("submitted_title", 60_000)
        assertEquals(SealState.READY_TO_SYNC, runBlocking { db.assessmentDraftDao().getActiveOnce() }!!.sealState)
        val items = runBlocking {
            val id = db.assessmentDraftDao().getActiveOnce()!!.id
            db.evidenceDraftDao().getAllForAssessmentOnce(id)
        }
        assertTrue(items.isNotEmpty())
        items.forEach { assertNotNull(runBlocking { db.assistanceDao().get(it.id)?.sealedSnapshotJson }) }
    }

    private fun openTask(task: String) {
        waitTag("task_list_lazy_column")
        ui.tapInLazyColumn("task_list_lazy_column", "task_card_$task")
        waitTag("btn_add_evidence")
    }
    private fun taskItems(task: String): List<EvidenceDraftEntity> = runBlocking {
        db.evidenceDraftDao().getAllForTaskOnce(db.assessmentDraftDao().getActiveOnce()!!.id, task)
    }
    private fun capturePhoto() {
        waitTag("btn_capture_shutter", 20_000)
        ui.tapTag("btn_capture_shutter")
        waitTag("btn_add_evidence", 30_000)
    }
    private fun openFirstPreview() {
        openRow(ui.onAllNodesWithTag("evidence_row").onFirst())
        waitTag("evidence_preview_size")
    }
    private fun openRow(row: SemanticsNodeInteraction) {
        // Tap the evidence icon area. The card's centre can lie over its nested
        // Replace/Remove buttons on a narrow phone; those are distinct actions.
        row.scrollToIfPossible().performTouchInput { click(Offset(20f, height / 2f)) }
    }
    private fun allowCapturePermissions(video: Boolean = false) {
        val context = instrumentation.targetContext
        val required = if (video) listOf(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO)
            else listOf(Manifest.permission.CAMERA)
        fun granted() = required.all { context.checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED }
        if (granted()) return
        waitTag("capture_permission_grant_button")
        ui.tapTag("capture_permission_grant_button")
        val device = UiDevice.getInstance(instrumentation)
        repeat(2) {
            if (granted()) return
            // The resource namespace differs between AOSP and Google's/OEM's
            // permission-controller APK. Match the actual OS button, never a
            // shell grant or a permission-related assumption/skip.
            val allow = device.wait(Until.findObject(By.res(Pattern.compile(".*:id/permission_allow_foreground_only_button"))), 5_000)
                ?: device.wait(Until.findObject(By.text(Pattern.compile("(?i)while using (?:the|this) app"))), 5_000)
            if (allow == null) device.dumpWindowHierarchy(File(context.filesDir, "p8-permission-dialog.xml"))
            assertNotNull("Expected the real OS permission dialog", allow)
            allow!!.click()
        }
        required.forEach { assertEquals(PackageManager.PERMISSION_GRANTED, context.checkSelfPermission(it)) }
    }
    private fun waitTag(tag: String, timeout: Long = 20_000) =
        ui.waitUntilExactlyOneExists(hasTestTag(tag), timeoutMillis = timeout)
    private fun waitFor(timeout: Long = 20_000, condition: () -> Boolean) = ui.waitUntil(timeoutMillis = timeout, condition = condition)
}
