package `in`.kaushalpramaan.app.data.assistance

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.data.draft.*
import `in`.kaushalpramaan.core.mapping.RulesLoader
import `in`.kaushalpramaan.core.seal.*
import java.util.UUID
import kotlinx.coroutines.*
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class AssistanceLifecycleTest {
    private lateinit var context: Context
    private lateinit var db: AppDatabase
    private lateinit var files: EvidenceFileManager
    private lateinit var repository: EvidenceRepository
    private lateinit var item: EvidenceDraftEntity
    private lateinit var record: AssistanceRecord
    @Before fun prepare() = runBlocking {
        context = ApplicationProvider.getApplicationContext()
        db = Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java).allowMainThreadQueries().build()
        files = object : EvidenceFileManager(context) { override fun availableInternalBytes() = 10L * 1024 * 1024 * 1024 }
        repository = EvidenceRepository(db.assessmentDraftDao(), db.taskDraftDao(), db.evidenceDraftDao(), files, RulesLoader.load())
        val assessment = repository.createOrResumeAssessment("TEST", "en", null)
        val capture = repository.beginCapture(assessment.id, "T1", EvidenceType.PHOTO, false) as BeginCaptureResult.Started
        capture.stagingFile.writeBytes(byteArrayOf(1, 2, 3))
        item = (repository.finalizeCapture(capture.evidenceId, true) as FinalizeResult.Ready).evidence
        record = AssistanceRecord(item.id, item.assessmentId, item.taskId, 1, "generation-1", item.relativePath,
            StreamingHasher.sha256Hex(repository.resolveFile(item)), null, "QUEUED", "queued", null, null, null)
        db.assistanceDao().put(record)
    }
    @After fun close() { db.close() }
    private fun result(r: AssistanceRecord) = AssistanceSnapshot(assessmentId = r.assessmentId, taskId = r.taskId,
        evidenceId = r.evidenceId, revisionId = "unsealed", revisionNumber = r.revisionNumber, mediaSha256 = r.inputSha256,
        status = AssistanceStatus.COMPLETED, quality = AssistanceAnalysis(AssistanceStatus.COMPLETED,
            AssistanceProvenance("quality-test", "test-profile", "a".repeat(64)), AssistanceCoverage(1, 1, 0), true),
        flags = listOf(AssistanceFlag(AssistanceFlagType.DARK, observed = 10.0, threshold = 60.0)), completedAtMillis = 1000)
    private fun runner(engine: AssistanceEngine = AssistanceEngine { r, _, _ -> result(r) }) = AssistanceRunner(db, files, engine)

    @Test fun completion_persists_and_repeat_job_never_runs_inference_again() = runBlocking {
        var runs = 0
        val runner = runner { r, _, stage -> runs++; stage("hands"); result(r) }
        runner.run(item.id, record.generation)
        val stored = db.assistanceDao().get(item.id)!!
        assertEquals("COMPLETED", stored.status)
        assertEquals(1, EvidenceAssistanceCoordinator.JSON.decodeFromString<AssistanceSnapshot>(stored.resultJson!!).flags.size)
        runner.run(item.id, record.generation)
        assertEquals(1, runs)
        assertEquals(item, db.evidenceDraftDao().getById(item.id))
    }

    private suspend fun delayedMutation(mutation: suspend () -> Unit) = coroutineScope {
        val started = CompletableDeferred<Unit>(); val release = CompletableDeferred<Unit>()
        val job = launch(Dispatchers.Default) { runner { r, _, _ -> started.complete(Unit); release.await(); result(r) }.run(item.id, record.generation) }
        started.await(); mutation(); release.complete(Unit); job.join()
    }

    @Test fun deletion_during_analysis_cascades_and_delayed_completion_cannot_resurrect_it() = runBlocking {
        delayedMutation { repository.deleteEvidence(item.id) }
        assertNull(db.assistanceDao().get(item.id))
    }
    @Test fun successful_retake_removes_only_old_record_and_stale_job_cannot_target_replacement() = runBlocking {
        var replacementId = ""
        delayedMutation {
            val capture = repository.beginCapture(item.assessmentId, "T1", EvidenceType.PHOTO, false, item.id) as BeginCaptureResult.Started
            capture.stagingFile.writeBytes(byteArrayOf(4, 5))
            replacementId = (repository.finalizeCapture(capture.evidenceId, true) as FinalizeResult.Ready).evidence.id
        }
        assertNull(db.assistanceDao().get(item.id))
        assertNull(db.assistanceDao().get(replacementId))
        assertNotNull(db.evidenceDraftDao().getById(replacementId))
    }
    @Test fun failed_retake_preserves_original_and_its_result() = runBlocking {
        runner().run(item.id, record.generation)
        val capture = repository.beginCapture(item.assessmentId, "T1", EvidenceType.PHOTO, false, item.id) as BeginCaptureResult.Started
        repository.finalizeCapture(capture.evidenceId, false)
        assertEquals("COMPLETED", db.assistanceDao().get(item.id)?.status)
    }
    @Test fun hash_mismatch_before_analysis_is_failure_and_never_bad_capture() = runBlocking {
        repository.resolveFile(item).appendBytes(byteArrayOf(8))
        var runs = 0
        runner { r, _, _ -> runs++; result(r) }.run(item.id, record.generation)
        assertEquals(0, runs)
        assertEquals("INPUT_CHANGED", db.assistanceDao().get(item.id)?.errorCategory)
        assertNull(db.assistanceDao().get(item.id)?.resultJson)
    }
    @Test fun changed_media_during_inference_discards_results() = runBlocking {
        delayedMutation { repository.resolveFile(item).appendBytes(byteArrayOf(9)) }
        assertEquals("INPUT_CHANGED", db.assistanceDao().get(item.id)?.errorCategory)
        assertNull(db.assistanceDao().get(item.id)?.resultJson)
    }
    @Test fun equivalent_bytes_moved_during_analysis_keep_the_same_valid_result() = runBlocking {
        val coordinator = EvidenceAssistanceCoordinator(context, db, files)
        delayedMutation {
            val original = repository.resolveFile(item)
            val final = java.io.File(original.parentFile, "equivalent-final.jpg")
            original.copyTo(final)
            db.evidenceDraftDao().update(item.copy(finalState = FinalEvidenceState.OPTIMIZED, finalRelativePath = files.relativePathOf(final)))
            coordinator.schedule(item.id)
        }
        assertEquals("COMPLETED", db.assistanceDao().get(item.id)?.status)
        assertNotNull(db.assistanceDao().get(item.id)?.resultJson)
        assertEquals(record.generation, db.assistanceDao().get(item.id)?.generation)
    }
    @Test fun cancellation_and_generation_change_prevent_old_job_overwrite() = runBlocking {
        delayedMutation { db.assistanceDao().put(record.copy(generation = "cancelled", status = "NOT_RUN", errorCategory = "CANCELLED")) }
        assertEquals("CANCELLED", db.assistanceDao().get(item.id)?.errorCategory)
        assertNull(db.assistanceDao().get(item.id)?.resultJson)
    }
    @Test fun revision_switch_prevents_old_job_from_updating_new_revision() = runBlocking {
        delayedMutation { val parent = db.assessmentDraftDao().getById(item.assessmentId)!!
            db.assessmentDraftDao().update(parent.copy(currentRevisionNumber = 2)) }
        assertNull(db.assistanceDao().get(item.id)?.resultJson)
    }
    @Test fun sealing_pending_is_immediate_and_snapshot_remains_immutable_after_late_completion() = runBlocking {
        val coordinator = EvidenceAssistanceCoordinator(context, db, files)
        var signed: AssistanceSnapshot? = null
        delayedMutation {
            val parent = db.assessmentDraftDao().getById(item.assessmentId)!!
            db.assessmentDraftDao().update(parent.copy(sealState = SealState.SEAL_IN_PROGRESS))
            signed = coordinator.snapshot(item, record.inputSha256, "sealed-revision", 1)
        }
        assertEquals(AssistanceStatus.RUNNING, signed!!.status)
        assertEquals(signed, coordinator.inherited(item))
        assertNull(db.assistanceDao().get(item.id)?.resultJson)
    }
    @Test fun completed_snapshot_is_bound_and_inherited_exactly() = runBlocking {
        runner().run(item.id, record.generation)
        val coordinator = EvidenceAssistanceCoordinator(context, db, files)
        val signed = coordinator.snapshot(item, record.inputSha256, "sealed-revision", 1)
        assertEquals(AssistanceStatus.COMPLETED, signed.status)
        assertEquals("sealed-revision", signed.revisionId)
        assertEquals(signed, coordinator.inherited(item))
        val changed = coordinator.snapshot(item, "c".repeat(64), "new-revision", 1)
        assertEquals(AssistanceStatus.NOT_RUN, changed.status)
        assertTrue(changed.flags.isEmpty())
    }
    @Test fun process_interruption_retries_running_work_and_failure_is_durable() = runBlocking {
        db.assistanceDao().put(record.copy(status = "RUNNING"))
        runner().run(item.id, record.generation)
        assertEquals("COMPLETED", db.assistanceDao().get(item.id)?.status)
        db.assistanceDao().put(record)
        runner().fail(item.id, record.generation, true)
        assertEquals("QUEUED", db.assistanceDao().get(item.id)?.status)
        runner().fail(item.id, record.generation, false)
        assertEquals("FAILED", db.assistanceDao().get(item.id)?.status)
    }
    @Test fun native_concurrency_is_bounded_across_runners() = runBlocking {
        val entered = CompletableDeferred<Unit>(); val release = CompletableDeferred<Unit>()
        val first = launch(Dispatchers.Default) { runner { r, _, _ -> entered.complete(Unit); release.await(); result(r) }.run(item.id, record.generation) }
        entered.await()
        var duplicateInvocations = 0
        val second = launch(Dispatchers.Default) { runner { r, _, _ -> duplicateInvocations++; result(r) }.run(item.id, record.generation) }
        release.complete(Unit); first.join(); second.join()
        assertEquals(0, duplicateInvocations)
    }
}
