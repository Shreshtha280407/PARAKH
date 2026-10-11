package `in`.kaushalpramaan.app.data.draft

import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.core.mapping.DeclarationContract
import `in`.kaushalpramaan.core.mapping.KeywordsFile
import `in`.kaushalpramaan.core.mapping.LinksFile
import `in`.kaushalpramaan.core.mapping.Rules
import `in`.kaushalpramaan.core.mapping.RulesLoader
import `in`.kaushalpramaan.core.mapping.TaskEntry
import `in`.kaushalpramaan.core.mapping.TasksFile
import `in`.kaushalpramaan.core.mapping.ThresholdsFile
import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import java.io.File
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * Exercises the real [EvidenceRepository] against the real Room entities/DAOs ([AppDatabase])
 * -- just with Room's default in-memory SQLite builder instead of the production SQLCipher
 * [net.sqlcipher.database.SupportFactory] swap, since SQLCipher's native library needs a real
 * device (see the connectedDebugAndroidTest-side SqlCipherEncryptionTest for that specific
 * claim). Every lifecycle/budget/reconciliation rule below is the actual production code
 * path, not a reimplementation.
 */
@RunWith(RobolectricTestRunner::class)
class EvidenceRepositoryTest {

    private lateinit var context: Context
    private lateinit var db: AppDatabase
    private lateinit var fileManager: EvidenceFileManager
    private lateinit var repository: EvidenceRepository
    private lateinit var rules: Rules

    @Before
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        db = Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java).allowMainThreadQueries().build()
        // Robolectric's StatFs shadow does not reflect the host's real free disk space, so the
        // default test fixture reports ample space -- the one test that specifically exercises
        // the INSUFFICIENT_FREE_SPACE branch builds its own repository with a tiny-space fake
        // instead of relying on this one.
        fileManager = object : EvidenceFileManager(context) {
            override fun availableInternalBytes(): Long = 10L * 1024 * 1024 * 1024
        }
        rules = RulesLoader.load()
        repository = EvidenceRepository(db.assessmentDraftDao(), db.taskDraftDao(), db.evidenceDraftDao(), fileManager, rules)
    }

    @After
    fun tearDown() {
        db.close()
    }

    // ---- fixed budgets (requirement: exact T1-T5 + total ceilings) ----

    @Test
    fun fixed_task_budgets_and_total_match_the_agreed_configuration() {
        val expected = mapOf(
            "T1" to 15_728_640L,
            "T2" to 20_971_520L,
            "T3" to 31_457_280L,
            "T4" to 26_214_400L,
            "T5" to 31_457_280L,
        )
        expected.forEach { (id, bytes) ->
            assertEquals(bytes, rules.tasksFile.tasks.first { it.id == id }.budgetBytes)
        }
        assertEquals(125_829_120L, rules.tasksFile.finalEvidenceBudgetBytes)
    }

    // ---- assessment/task lifecycle ----

    @Test
    fun createOrResumeAssessment_creates_exactly_the_five_fixed_tasks_with_canonical_budgets() = runTest {
        val assessment = repository.createOrResumeAssessment(workerId = "KP-TEST", language = "en", matchOutput = null)

        assertTrue(assessment.isTestOnly)
        assertEquals(AssessmentDraftState.ACTIVE, assessment.state)

        val tasks = db.taskDraftDao().getAllOnce(assessment.id)
        assertEquals(5, tasks.size)
        assertEquals(setOf("T1", "T2", "T3", "T4", "T5"), tasks.map { it.taskId }.toSet())
        assertEquals(15_728_640L, tasks.first { it.taskId == "T1" }.budgetBytes)
        assertTrue(tasks.all { it.state == TaskDraftState.NO_EVIDENCE && it.evidenceCount == 0 && it.capturedBytes == 0L })
    }

    @Test
    fun createOrResumeAssessment_is_idempotent_and_reuses_the_one_active_draft() = runTest {
        val first = repository.createOrResumeAssessment("w1", "en", null)
        val second = repository.createOrResumeAssessment("w2", "hi", null)
        assertEquals(first.id, second.id)
        assertEquals(5, db.taskDraftDao().getAllOnce(first.id).size) // still exactly 5 task rows, not 10
    }

    // ---- capture lifecycle: begin -> finalize (success/failure) ----

    @Test
    fun begin_then_finalize_success_promotes_the_file_and_updates_the_task_draft() = runTest {
        val assessment = repository.createOrResumeAssessment("w", "en", null)
        val begin = repository.beginCapture(assessment.id, "T1", EvidenceType.PHOTO, debugOverrideRequested = false)
        check(begin is BeginCaptureResult.Started)
        writeFakeBytes(begin.stagingFile, 1_000)

        val result = repository.finalizeCapture(begin.evidenceId, success = true, actualByteSize = 1_000L, widthPx = 100, heightPx = 200)

        assertTrue(result is FinalizeResult.Ready)
        assertFalse(begin.stagingFile.exists())
        val readyFile = fileManager.finalFile(assessment.id, "T1", begin.evidenceId, EvidenceType.PHOTO)
        assertTrue(readyFile.exists())
        val taskDraft = db.taskDraftDao().getOne(assessment.id, "T1")!!
        assertEquals(TaskDraftState.READY, taskDraft.state)
        assertEquals(1, taskDraft.evidenceCount)
        assertEquals(1_000L, taskDraft.capturedBytes)
    }

    @Test
    fun finalize_failure_marks_failed_deletes_staging_bytes_and_recomputes_task_state() = runTest {
        val assessment = repository.createOrResumeAssessment("w", "en", null)
        val begin = repository.beginCapture(assessment.id, "T1", EvidenceType.PHOTO, false)
        check(begin is BeginCaptureResult.Started)
        writeFakeBytes(begin.stagingFile, 10)

        val result = repository.finalizeCapture(begin.evidenceId, success = false)

        assertTrue(result is FinalizeResult.Failed)
        assertFalse(begin.stagingFile.exists())
        val taskDraft = db.taskDraftDao().getOne(assessment.id, "T1")!!
        assertEquals(TaskDraftState.FAILED, taskDraft.state)
        assertEquals(0, taskDraft.evidenceCount)
        assertEquals(0L, taskDraft.capturedBytes)
    }

    @Test
    fun cancelCapture_leaves_no_trace_at_all() = runTest {
        val assessment = repository.createOrResumeAssessment("w", "en", null)
        val begin = repository.beginCapture(assessment.id, "T1", EvidenceType.VIDEO, false)
        check(begin is BeginCaptureResult.Started)
        writeFakeBytes(begin.stagingFile, 10)

        repository.cancelCapture(begin.evidenceId)

        assertFalse(begin.stagingFile.exists())
        assertNull(db.evidenceDraftDao().getById(begin.evidenceId))
        val taskDraft = db.taskDraftDao().getOne(assessment.id, "T1")!!
        assertEquals(TaskDraftState.NO_EVIDENCE, taskDraft.state)
    }

    // ---- budget enforcement ----

    @Test
    fun begin_capture_is_rejected_once_the_single_tasks_own_budget_is_exhausted() = runTest {
        val assessment = repository.createOrResumeAssessment("w", "en", null)
        completeReadyEvidence(assessment.id, "T1", EvidenceType.PHOTO, 15_728_640L)

        val begin = repository.beginCapture(assessment.id, "T1", EvidenceType.PHOTO, false)

        check(begin is BeginCaptureResult.Rejected)
        assertEquals(CaptureRejectionReason.TASK_BUDGET_EXHAUSTED, begin.reason)
    }

    @Test
    fun begin_capture_is_rejected_by_total_budget_even_when_the_requested_task_still_has_room() = runTest {
        // Synthetic rules where the total ceiling is deliberately tighter than any single
        // task's own budget -- the real canonical pack's total exactly equals the sum of its
        // five task budgets, so this distinct "task has room but the total doesn't" branch
        // can only be exercised with a fixture, not the real packs/ae-con-q0602 data.
        val tightRepo = repositoryWithSyntheticBudgets(mapOf("T1" to 10_000_000L, "T2" to 10_000_000L), totalBudget = 8_000_000L)
        val assessment = tightRepo.createOrResumeAssessment("w", "en", null)
        completeReadyEvidence(tightRepo, assessment.id, "T2", EvidenceType.PHOTO, 8_000_000L)

        val begin = tightRepo.beginCapture(assessment.id, "T1", EvidenceType.PHOTO, false)

        check(begin is BeginCaptureResult.Rejected)
        assertEquals(CaptureRejectionReason.TOTAL_BUDGET_EXHAUSTED, begin.reason)
    }

    @Test
    fun begin_capture_is_rejected_when_free_space_is_below_300_mb() = runTest {
        val tightSpaceFileManager = object : EvidenceFileManager(context) {
            override fun availableInternalBytes(): Long = 1_000L
        }
        val repo = EvidenceRepository(db.assessmentDraftDao(), db.taskDraftDao(), db.evidenceDraftDao(), tightSpaceFileManager, rules)
        val assessment = repo.createOrResumeAssessment("w", "en", null)

        val begin = repo.beginCapture(assessment.id, "T1", EvidenceType.PHOTO, false)

        check(begin is BeginCaptureResult.Rejected)
        assertEquals(CaptureRejectionReason.INSUFFICIENT_FREE_SPACE, begin.reason)
    }

    @Test
    fun debug_only_ceiling_override_is_applied_only_when_both_the_flag_and_the_request_are_true() = runTest {
        val assessment = repository.createOrResumeAssessment("w", "en", null)
        val begin = repository.beginCapture(assessment.id, "T3", EvidenceType.VIDEO, debugOverrideRequested = true)
        check(begin is BeginCaptureResult.Started)
        // BuildConfig.P4_TEST_ONLY_CEILING_ENABLED is true in the debug variant these tests
        // compile against (see app/build.gradle.kts) -- so requesting the override here
        // must cap the ceiling at BuildConfig.P4_TEST_ONLY_CEILING_BYTES, not T3's real 30MB.
        assertEquals(`in`.kaushalpramaan.app.BuildConfig.P4_TEST_ONLY_CEILING_BYTES, begin.ceilingBytes)
    }

    // ---- replace: old item preserved until new item is READY, then removed ----

    @Test
    fun replace_keeps_the_old_ready_item_until_the_new_one_finalizes() = runTest {
        val assessment = repository.createOrResumeAssessment("w", "en", null)
        val oldId = completeReadyEvidence(assessment.id, "T1", EvidenceType.PHOTO, 1_000_000L)

        val begin = repository.beginCapture(assessment.id, "T1", EvidenceType.PHOTO, false, replacesEvidenceId = oldId)
        check(begin is BeginCaptureResult.Started)
        writeFakeBytes(begin.stagingFile, 500_000)

        // Not finalized yet: the old item must still be present and READY.
        assertEquals(EvidenceDraftState.READY, db.evidenceDraftDao().getById(oldId)?.state)

        repository.finalizeCapture(begin.evidenceId, success = true, actualByteSize = 500_000L)

        // Now finalized: the old item is gone (row + file), only the new one remains.
        assertNull(db.evidenceDraftDao().getById(oldId))
        val remaining = db.evidenceDraftDao().getAllForTaskOnce(assessment.id, "T1")
        assertEquals(1, remaining.size)
        assertEquals(begin.evidenceId, remaining.first().id)
        val taskDraft = db.taskDraftDao().getOne(assessment.id, "T1")!!
        assertEquals(500_000L, taskDraft.capturedBytes)
    }

    @Test
    fun replace_credits_back_the_old_items_bytes_so_a_fully_used_budget_can_still_replace() = runTest {
        val assessment = repository.createOrResumeAssessment("w", "en", null)
        val oldId = completeReadyEvidence(assessment.id, "T1", EvidenceType.PHOTO, 15_728_640L) // T1's full budget

        val begin = repository.beginCapture(assessment.id, "T1", EvidenceType.PHOTO, false, replacesEvidenceId = oldId)

        check(begin is BeginCaptureResult.Started)
        assertEquals(15_728_640L, begin.ceilingBytes)
    }

    // ---- delete ----

    @Test
    fun delete_removes_the_row_and_the_file_and_recomputes_the_task_draft() = runTest {
        val assessment = repository.createOrResumeAssessment("w", "en", null)
        val id = completeReadyEvidence(assessment.id, "T2", EvidenceType.VIDEO, 2_000_000L)
        val file = fileManager.finalFile(assessment.id, "T2", id, EvidenceType.VIDEO)
        assertTrue(file.exists())

        repository.deleteEvidence(id)

        assertFalse(file.exists())
        assertNull(db.evidenceDraftDao().getById(id))
        val taskDraft = db.taskDraftDao().getOne(assessment.id, "T2")!!
        assertEquals(TaskDraftState.NO_EVIDENCE, taskDraft.state)
        assertEquals(0L, taskDraft.capturedBytes)
    }

    @Test
    fun deleteAssessment_removes_everything_and_active_assessment_becomes_null() = runTest {
        val assessment = repository.createOrResumeAssessment("w", "en", null)
        completeReadyEvidence(assessment.id, "T1", EvidenceType.PHOTO, 1_000L)

        repository.deleteAssessment(assessment.id)

        assertNull(repository.getActiveAssessment())
        assertTrue(db.taskDraftDao().getAllOnce(assessment.id).isEmpty())
        assertFalse(fileManager.assessmentDir(assessment.id).exists())
    }

    // ---- launch-time reconciliation: crash recovery ----

    @Test
    fun reconcile_finishes_an_interrupted_capture_whose_rename_already_succeeded() = runTest {
        // Simulates: process died after the file was renamed to its final name but before
        // the DB row was updated to READY -- the row is still STAGING, pointing at the
        // (now-gone) staging path, while the final file already exists on disk.
        val assessment = repository.createOrResumeAssessment("w", "en", null)
        val begin = repository.beginCapture(assessment.id, "T1", EvidenceType.PHOTO, false)
        check(begin is BeginCaptureResult.Started)
        val finalFile = fileManager.finalFile(assessment.id, "T1", begin.evidenceId, EvidenceType.PHOTO)
        writeFakeBytes(finalFile, 4_242)
        begin.stagingFile.delete() // the rename already happened in this simulated crash window

        repository.reconcileOnLaunch()

        val row = db.evidenceDraftDao().getById(begin.evidenceId)!!
        assertEquals(EvidenceDraftState.READY, row.state)
        assertEquals(4_242L, row.byteSize)
        val taskDraft = db.taskDraftDao().getOne(assessment.id, "T1")!!
        assertEquals(1, taskDraft.evidenceCount)
    }

    @Test
    fun reconcile_fails_cleanly_an_interrupted_capture_that_never_produced_a_final_file() = runTest {
        // Simulates: process died mid-capture, before CameraX ever finished writing -- only
        // a partial staging file (or none at all) exists, no final file anywhere.
        val assessment = repository.createOrResumeAssessment("w", "en", null)
        val begin = repository.beginCapture(assessment.id, "T1", EvidenceType.PHOTO, false)
        check(begin is BeginCaptureResult.Started)
        writeFakeBytes(begin.stagingFile, 100) // partial bytes only

        repository.reconcileOnLaunch()

        val row = db.evidenceDraftDao().getById(begin.evidenceId)!!
        assertEquals(EvidenceDraftState.FAILED, row.state)
        assertFalse(begin.stagingFile.exists())
    }

    @Test
    fun reconcile_finishes_a_delete_that_was_interrupted_after_being_marked() = runTest {
        val assessment = repository.createOrResumeAssessment("w", "en", null)
        val id = completeReadyEvidence(assessment.id, "T1", EvidenceType.PHOTO, 1_000L)
        val file = fileManager.finalFile(assessment.id, "T1", id, EvidenceType.PHOTO)
        // Simulate: markDeleted() committed, but the file removal + hard-delete never ran.
        db.evidenceDraftDao().markDeleted(id)

        repository.reconcileOnLaunch()

        assertFalse(file.exists())
        assertNull(db.evidenceDraftDao().getById(id))
    }

    @Test
    fun reconcile_finishes_an_interrupted_replace_by_removing_the_stale_old_item() = runTest {
        val assessment = repository.createOrResumeAssessment("w", "en", null)
        val oldId = completeReadyEvidence(assessment.id, "T1", EvidenceType.PHOTO, 1_000L)
        val begin = repository.beginCapture(assessment.id, "T1", EvidenceType.PHOTO, false, replacesEvidenceId = oldId)
        check(begin is BeginCaptureResult.Started)
        writeFakeBytes(begin.stagingFile, 2_000)
        // Simulate: the new item's finalize committed as READY, but the forward-delete of
        // the old item it replaces never ran (process died in between).
        val newFinal = fileManager.finalFile(assessment.id, "T1", begin.evidenceId, EvidenceType.PHOTO)
        fileManager.promote(begin.stagingFile, newFinal)
        val newRow = db.evidenceDraftDao().getById(begin.evidenceId)!!
        db.evidenceDraftDao().update(newRow.copy(relativePath = fileManager.relativePathOf(newFinal), byteSize = 2_000L, state = EvidenceDraftState.READY))

        repository.reconcileOnLaunch()

        assertNull(db.evidenceDraftDao().getById(oldId))
        val finishedNewRow = db.evidenceDraftDao().getById(begin.evidenceId)!!
        assertNull(finishedNewRow.replacesEvidenceId)
        val remaining = db.evidenceDraftDao().getAllForTaskOnce(assessment.id, "T1")
        assertEquals(1, remaining.size)
    }

    @Test
    fun reconcile_sweeps_true_orphan_files_but_never_touches_another_tasks_valid_evidence() = runTest {
        val assessment = repository.createOrResumeAssessment("w", "en", null)
        val validId = completeReadyEvidence(assessment.id, "T2", EvidenceType.PHOTO, 1_000L)
        val validFile = fileManager.finalFile(assessment.id, "T2", validId, EvidenceType.PHOTO)
        val orphan = fileManager.finalFile(assessment.id, "T3", "orphan-evidence-id", EvidenceType.PHOTO)
        writeFakeBytes(orphan, 50)

        repository.reconcileOnLaunch()

        assertTrue(validFile.exists())
        assertFalse(orphan.exists())
    }

    @Test
    fun reconcile_finishes_an_assessment_delete_that_was_interrupted_after_being_marked() = runTest {
        val assessment = repository.createOrResumeAssessment("w", "en", null)
        completeReadyEvidence(assessment.id, "T1", EvidenceType.PHOTO, 1_000L)
        db.assessmentDraftDao().markDeleted(assessment.id, nowMillis = 123L)

        repository.reconcileOnLaunch()

        assertNull(db.assessmentDraftDao().getById(assessment.id))
        assertFalse(fileManager.assessmentDir(assessment.id).exists())
    }

    // ---- test helpers ----

    private fun writeFakeBytes(file: File, size: Int) {
        file.parentFile?.mkdirs()
        file.writeBytes(ByteArray(size))
    }

    private suspend fun completeReadyEvidence(assessmentId: String, taskId: String, kind: EvidenceType, bytes: Long): String =
        completeReadyEvidence(repository, assessmentId, taskId, kind, bytes)

    private suspend fun completeReadyEvidence(repo: EvidenceRepository, assessmentId: String, taskId: String, kind: EvidenceType, bytes: Long): String {
        val begin = repo.beginCapture(assessmentId, taskId, kind, debugOverrideRequested = false)
        check(begin is BeginCaptureResult.Started) { "expected capture to start, got $begin" }
        writeFakeBytes(begin.stagingFile, bytes.toInt())
        val result = repo.finalizeCapture(begin.evidenceId, success = true, actualByteSize = bytes)
        check(result is FinalizeResult.Ready)
        return begin.evidenceId
    }

    private fun repositoryWithSyntheticBudgets(taskBudgets: Map<String, Long>, totalBudget: Long): EvidenceRepository {
        val syntheticRules = Rules(
            links = LinksFile(matchRulesId = "test", cards = emptyList(), tools = emptyList()),
            keywords = KeywordsFile(cards = emptyMap()),
            thresholds = ThresholdsFile(
                matchRulesId = "test",
                answerStrength = emptyMap(),
                practicalNosForMatching = emptyList(),
                declarationContract = DeclarationContract(cardCount = 0, toolCount = 0),
            ),
            nosTask = emptyMap(),
            tasksFile = TasksFile(
                qpCode = "TEST",
                qpVersion = "v0",
                finalEvidenceBudgetMb = (totalBudget / (1024 * 1024)).toInt(),
                finalEvidenceBudgetBytes = totalBudget,
                tasks = taskBudgets.map { (id, bytes) -> TaskEntry(id = id, nos = "NOS-$id", budgetBytes = bytes) },
            ),
        )
        return EvidenceRepository(db.assessmentDraftDao(), db.taskDraftDao(), db.evidenceDraftDao(), fileManager, syntheticRules)
    }
}
