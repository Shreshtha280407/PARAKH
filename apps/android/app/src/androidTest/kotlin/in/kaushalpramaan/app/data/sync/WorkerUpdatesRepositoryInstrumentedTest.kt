package `in`.kaushalpramaan.app.data.sync

import `in`.kaushalpramaan.app.data.draft.AppDatabase
import `in`.kaushalpramaan.app.data.draft.EvidenceFileManager
import `in`.kaushalpramaan.app.data.draft.EvidenceRepository
import `in`.kaushalpramaan.app.data.draft.SealState
import `in`.kaushalpramaan.core.mapping.RulesLoader
import android.os.StrictMode
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class WorkerUpdatesRepositoryInstrumentedTest {
    @Test
    fun manual_poll_from_main_thread_applies_task_locks_and_repeated_poll_preserves_attestation() = runBlocking {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val db = AppDatabase.build(context, "kp_updates_test_${System.nanoTime()}.db")
        val server = MockWebServer()
        server.start()
        try {
            val evidence = EvidenceRepository(db.assessmentDraftDao(), db.taskDraftDao(), db.evidenceDraftDao(), EvidenceFileManager(context), RulesLoader.load())
            val assessment = evidence.createOrResumeAssessment("KP-UPDATES-TEST", "en", null)
            db.assessmentDraftDao().update(assessment.copy(serverAssessmentId = 42, serverWorkerToken = "test-capability", sealState = SealState.READY_TO_SYNC, syncedAtMillis = 1000, attestationConfirmed = true))
            val body = """{"assessment_id":42,"assessment_status":"needs_reassessment","revision_number":2,"report_status":"pending","latest_event_id":17,"pending_reassessment_request":{"id":7,"assessment_id":42,"revision_number":2,"task_codes":["T2"],"reason":"The meter reading is not visible.","capture_instructions":"Recapture T2 with the reading in focus.","requested_by_id":1,"requested_at":"2026-10-14T00:00:00Z","status":"pending"}}"""
            val baseUrl = server.url("/").toString().removeSuffix("/")
            val endpoint = object : SyncEndpointConfig {
                override fun baseUrl() = baseUrl
                override fun supportsRuntimeOverride() = true
                override fun setOverrideBaseUrl(url: String?) {}
            }
            val repository = WorkerUpdatesRepository(db.assessmentDraftDao(), db.taskDraftDao(), endpoint)
            suspend fun pollOnMain(responseBody: String = body): WorkerUpdatesPollResult {
                server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(responseBody))
                return withContext(Dispatchers.Main) {
                    val original = StrictMode.getThreadPolicy()
                    StrictMode.setThreadPolicy(StrictMode.ThreadPolicy.Builder(original).detectNetwork().penaltyDeathOnNetwork().build())
                    try { repository.pollAndApply(assessment.id) } finally { StrictMode.setThreadPolicy(original) }
                }
            }
            assertTrue(pollOnMain() is WorkerUpdatesPollResult.Applied)
            assertTrue(db.taskDraftDao().getAllOnce(assessment.id).single { it.taskId == "T1" }.locked)
            assertFalse(db.taskDraftDao().getAllOnce(assessment.id).single { it.taskId == "T2" }.locked)
            val applied = db.assessmentDraftDao().getById(assessment.id)!!
            assertEquals("T2", applied.pendingReassessmentTaskCodesCsv)
            assertEquals("The meter reading is not visible.", applied.pendingReassessmentReason)
            assertEquals("Recapture T2 with the reading in focus.", applied.pendingReassessmentCaptureInstructions)
            assertEquals(17L, applied.workerUpdatesCursor)
            assertEquals(SealState.DRAFT_EDITABLE, applied.sealState)
            assertFalse(applied.attestationConfirmed)
            assertEquals(1000L, applied.syncedAtMillis)

            db.assessmentDraftDao().update(applied.copy(sealState = SealState.FINAL_REVIEW_READY, attestationConfirmed = true))
            assertTrue(pollOnMain() is WorkerUpdatesPollResult.Applied)
            val repeated = db.assessmentDraftDao().getById(assessment.id)!!
            assertTrue(repeated.attestationConfirmed)
            assertEquals(SealState.FINAL_REVIEW_READY, repeated.sealState)
            val newerRequest = body.replace("\"revision_number\":2", "\"revision_number\":3")
                .replace("\"id\":7", "\"id\":8").replace("\"latest_event_id\":17", "\"latest_event_id\":18")
            assertTrue(pollOnMain(newerRequest) is WorkerUpdatesPollResult.Applied)
            val reopenedAgain = db.assessmentDraftDao().getById(assessment.id)!!
            assertEquals("a later request must reopen editing even before the old pending banner was cleared", SealState.DRAFT_EDITABLE, reopenedAgain.sealState)
            assertFalse(reopenedAgain.attestationConfirmed)
            assertEquals(3, reopenedAgain.currentRevisionNumber)
            assertEquals(18L, reopenedAgain.workerUpdatesCursor)
            assertEquals("/assessments/42/worker-updates?since=0", server.takeRequest().path)
            assertEquals("/assessments/42/worker-updates?since=17", server.takeRequest().path)
            assertEquals("/assessments/42/worker-updates?since=17", server.takeRequest().path)
        } finally {
            server.shutdown()
            db.close()
        }
    }
}
