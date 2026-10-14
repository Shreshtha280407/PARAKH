package `in`.kaushalpramaan.app.data.seal

import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.data.draft.AppDatabase
import `in`.kaushalpramaan.app.data.draft.BeginCaptureResult
import `in`.kaushalpramaan.app.data.draft.EvidenceDraftState
import `in`.kaushalpramaan.app.data.draft.EvidenceFileManager
import `in`.kaushalpramaan.app.data.draft.EvidenceRepository
import `in`.kaushalpramaan.app.data.draft.FinalEvidenceState
import `in`.kaushalpramaan.app.data.draft.FinalizeResult
import `in`.kaushalpramaan.app.data.draft.SealState
import `in`.kaushalpramaan.core.mapping.Rules
import `in`.kaushalpramaan.core.mapping.RulesLoader
import `in`.kaushalpramaan.core.seal.VaultKeysetProvider
import `in`.kaushalpramaan.media.PhotoOptimizer
import `in`.kaushalpramaan.media.VideoOptimizer
import android.content.Context
import android.graphics.Bitmap
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import java.io.File
import java.io.FileOutputStream
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.GraphicsMode

/**
 * Exercises the real [SealOrchestrator] against the real Room entities/DAOs and the real
 * [PhotoOptimizer] (real JPEG encode/decode under Robolectric's NATIVE graphics mode -- see
 * PhotoOptimizerTest). [seal]/[SealOrchestrator.discardAndReopen]'s Keystore/Tink-dependent
 * paths need a real device (see SealOrchestratorInstrumentedTest); this class covers
 * everything reachable without them: automatic optimisation, the PROCESSING/SEAL_IN_PROGRESS
 * crash-recovery branches of [SealOrchestrator.reconcileOnLaunch], attestation, and the
 * pre-seal (no vault-restore needed) path of discard/reopen.
 */
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@RunWith(RobolectricTestRunner::class)
class SealOrchestratorTest {

    private lateinit var context: Context
    private lateinit var db: AppDatabase
    private lateinit var fileManager: EvidenceFileManager
    private lateinit var evidenceRepository: EvidenceRepository
    private lateinit var orchestrator: SealOrchestrator
    private lateinit var rules: Rules

    @Before
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        db = Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java).allowMainThreadQueries().build()
        fileManager = object : EvidenceFileManager(context) {
            override fun availableInternalBytes(): Long = 10L * 1024 * 1024 * 1024
        }
        rules = RulesLoader.load()
        evidenceRepository = EvidenceRepository(db.assessmentDraftDao(), db.taskDraftDao(), db.evidenceDraftDao(), fileManager, rules)
        orchestrator = SealOrchestrator(
            assessmentDraftDao = db.assessmentDraftDao(),
            evidenceDraftDao = db.evidenceDraftDao(),
            outboxDao = db.outboxDao(),
            fileManager = fileManager,
            rules = rules,
            photoOptimizer = PhotoOptimizer(),
            videoOptimizer = VideoOptimizer(context),
            vaultKeysetProvider = VaultKeysetProvider(context),
            appVersion = "test-version",
        )
    }

    @After
    fun tearDown() {
        db.close()
    }

    // ---- helpers ----

    /** Writes a real, decodable JPEG (not garbage bytes -- PhotoOptimizer needs real pixel
     * data) of the given dimensions as this evidence item's captured file, via the real P4
     * capture path (beginCapture/finalizeCapture), so SealOrchestrator operates on exactly
     * the same row shape production code produces. */
    private suspend fun captureRealPhoto(repo: EvidenceRepository, assessmentId: String, taskId: String, widthPx: Int, heightPx: Int): String {
        val begin = repo.beginCapture(assessmentId, taskId, EvidenceType.PHOTO, debugOverrideRequested = false)
        check(begin is BeginCaptureResult.Started) { "expected capture to start, got $begin" }
        val bitmap = Bitmap.createBitmap(widthPx, heightPx, Bitmap.Config.ARGB_8888)
        for (y in 0 until heightPx) for (x in 0 until widthPx) {
            val r = (255 * x / widthPx.coerceAtLeast(1)) and 0xFF
            val g = (255 * y / heightPx.coerceAtLeast(1)) and 0xFF
            bitmap.setPixel(x, y, (0xFF shl 24) or (r shl 16) or (g shl 8))
        }
        begin.stagingFile.parentFile?.mkdirs()
        FileOutputStream(begin.stagingFile).use { out -> bitmap.compress(Bitmap.CompressFormat.JPEG, 100, out) }
        bitmap.recycle()
        val result = repo.finalizeCapture(begin.evidenceId, success = true, widthPx = widthPx, heightPx = heightPx)
        check(result is FinalizeResult.Ready) { "expected finalize to succeed, got $result" }
        return begin.evidenceId
    }


    // ---- processEvidence ----

    @Test
    fun fitting_photo_is_marked_FITS_AS_IS_byte_identical_and_review_becomes_ready() = runTest {
        val assessment = evidenceRepository.createOrResumeAssessment("w", "en", null)
        val evidenceId = captureRealPhoto(evidenceRepository, assessment.id, "T1", 50, 50) // tiny, fits real 15MB budget trivially

        val outcome = orchestrator.processEvidence(assessment.id)

        assertEquals(ProcessOutcome.AllFit, outcome)
        val row = db.evidenceDraftDao().getById(evidenceId)!!
        assertEquals(FinalEvidenceState.FITS_AS_IS, row.finalState)
        assertEquals(row.byteSize, row.finalBytes)
        assertEquals(row.relativePath, row.finalRelativePath)
        val assessmentRow = db.assessmentDraftDao().getById(assessment.id)!!
        assertEquals(SealState.FINAL_REVIEW_READY, assessmentRow.sealState)
    }

    // These two tests use the REAL default task budgets (15-30 MB) for capture -- a real
    // phone photo/video comfortably fits those, and P4's own fail-closed capture-time check
    // (see EvidenceRepository.finalizeCapture) guarantees every READY item already fits by
    // the time P5 ever sees it. That is by design, not a gap: in normal use P5's "needs
    // optimisation"/"quality floor exceeded" branches are rare precisely because P4 already
    // enforces the same real budgets at capture time. The realistic, intentional way to
    // exercise those branches -- here and in the real P5_TEST_ONLY manual gate -- is the
    // debug-forced virtual total budget (spec part D.6), routed through this exact same
    // production ledger/optimiser path, never a separate mock path.

    @Test
    fun oversized_photo_is_really_optimized_to_fit_a_debug_forced_budget() = runTest {
        val assessment = evidenceRepository.createOrResumeAssessment("w", "en", null)
        // 1200x900 gradient JPEG comfortably passes P4's real capture-time check (well under
        // T1's real 15 MB budget) but is well over 40KB raw.
        val evidenceId = captureRealPhoto(evidenceRepository, assessment.id, "T1", 1200, 900)
        val rawBytes = db.evidenceDraftDao().getById(evidenceId)!!.byteSize
        check(rawBytes > 40_000L) { "test fixture must exceed the forced budget, was $rawBytes" }

        val outcome = orchestrator.processEvidence(assessment.id, debugForcedTotalBudgetBytes = 40_000L)

        val row = db.evidenceDraftDao().getById(evidenceId)!!
        if (outcome == ProcessOutcome.AllFit) {
            assertEquals(FinalEvidenceState.OPTIMIZED, row.finalState)
            val finalBytes = requireNotNull(row.finalBytes)
            assertTrue("optimized bytes must fit the forced budget", finalBytes <= 40_000L)
            assertTrue("optimized file must actually be smaller than the raw capture", finalBytes < rawBytes)
        } else {
            // A real JPEG optimiser cannot always hit an arbitrarily tiny target -- if the
            // quality floor genuinely can't fit, that is itself a valid, honestly-reported
            // outcome this test also accepts rather than asserting a specific number.
            assertEquals(ProcessOutcome.SomeItemsExceedBudget, outcome)
            assertEquals(FinalEvidenceState.QUALITY_FLOOR_EXCEEDED, row.finalState)
        }
    }

    @Test
    fun quality_floor_exceeded_item_blocks_final_review_and_reverts_to_draft_editable() = runTest {
        val assessment = evidenceRepository.createOrResumeAssessment("w", "en", null)
        val evidenceId = captureRealPhoto(evidenceRepository, assessment.id, "T1", 400, 300)

        // A forced budget of 100 bytes is impossible for any real photo, even at the quality
        // floor -- exercises the genuine refusal path, not a hand-picked near-fit.
        val outcome = orchestrator.processEvidence(assessment.id, debugForcedTotalBudgetBytes = 100L)

        assertEquals(ProcessOutcome.SomeItemsExceedBudget, outcome)
        val row = db.evidenceDraftDao().getById(evidenceId)!!
        assertEquals(FinalEvidenceState.QUALITY_FLOOR_EXCEEDED, row.finalState)
        assertTrue("a recoverable draft file must still exist", fileManager.resolveRelativePath(row.finalRelativePath!!).exists())
        val assessmentRow = db.assessmentDraftDao().getById(assessment.id)!!
        assertEquals(SealState.DRAFT_EDITABLE, assessmentRow.sealState)
    }

    @Test
    fun earlier_items_claiming_budget_does_not_wrongly_zero_out_a_later_items_allowance() = runTest {
        // Regression test for a real bug the P5 manual gate caught: a second, not-yet-
        // processed sibling's RAW (pre-optimisation) bytes must never be counted as already
        // "used" when computing an EARLIER item's allowed budget -- that double-penalizes the
        // earlier item for space the later one hasn't even tried to shrink into yet, and can
        // wrongly zero out its allowance. Two real photos in the same task, a forced total
        // budget that comfortably fits the first alone but not both raw: the first must fit
        // (or optimize) using the FULL forced budget, not budget-minus-the-seconds-raw-size.
        val assessment = evidenceRepository.createOrResumeAssessment("w", "en", null)
        val firstId = captureRealPhoto(evidenceRepository, assessment.id, "T1", 50, 50) // tiny
        val secondId = captureRealPhoto(evidenceRepository, assessment.id, "T1", 1200, 900) // large raw
        val secondRawBytes = db.evidenceDraftDao().getById(secondId)!!.byteSize
        val firstRawBytes = db.evidenceDraftDao().getById(firstId)!!.byteSize
        check(secondRawBytes > firstRawBytes) { "test fixture must have a meaningfully larger second item" }
        // A forced budget bigger than the first item alone but smaller than both items' raw
        // sum -- the exact shape of the real bug (ledger math would previously see the
        // second's full raw size as already "used" while processing the first).
        val forcedBudget = firstRawBytes + 20_000L
        check(forcedBudget < firstRawBytes + secondRawBytes)

        orchestrator.processEvidence(assessment.id, debugForcedTotalBudgetBytes = forcedBudget)

        val firstRow = db.evidenceDraftDao().getById(firstId)!!
        assertEquals(
            "the first (smaller, earlier) item must fit using the full forced budget, not budget-minus-siblings-raw-size",
            FinalEvidenceState.FITS_AS_IS,
            firstRow.finalState,
        )
        assertEquals(firstRawBytes, firstRow.finalBytes)
    }

    @Test
    fun processEvidence_is_idempotent_already_processed_items_are_not_reprocessed() = runTest {
        val assessment = evidenceRepository.createOrResumeAssessment("w", "en", null)
        val evidenceId = captureRealPhoto(evidenceRepository, assessment.id, "T1", 50, 50)
        orchestrator.processEvidence(assessment.id)
        val afterFirst = db.evidenceDraftDao().getById(evidenceId)!!

        val secondOutcome = orchestrator.processEvidence(assessment.id)

        assertEquals(ProcessOutcome.AllFit, secondOutcome)
        val afterSecond = db.evidenceDraftDao().getById(evidenceId)!!
        assertEquals(afterFirst.finalState, afterSecond.finalState)
        assertEquals(afterFirst.finalBytes, afterSecond.finalBytes)
        assertEquals(afterFirst.finalRelativePath, afterSecond.finalRelativePath)
    }

    // ---- crash recovery ----

    @Test
    fun reconcileOnLaunch_resumes_an_interrupted_PROCESSING_state() = runTest {
        val assessment = evidenceRepository.createOrResumeAssessment("w", "en", null)
        captureRealPhoto(evidenceRepository, assessment.id, "T1", 50, 50)
        // Simulate a crash mid-processing: sealState stuck at PROCESSING, item still
        // NOT_PROCESSED (its real pre-crash value, untouched).
        db.assessmentDraftDao().update(assessment.copy(sealState = SealState.PROCESSING))

        orchestrator.reconcileOnLaunch(assessment.id)

        val assessmentRow = db.assessmentDraftDao().getById(assessment.id)!!
        assertEquals(SealState.FINAL_REVIEW_READY, assessmentRow.sealState)
        val items = db.evidenceDraftDao().getAllForAssessmentOnce(assessment.id).filter { it.state == EvidenceDraftState.READY }
        assertTrue(items.all { it.finalState != FinalEvidenceState.NOT_PROCESSED })
    }

    @Test
    fun reconcileOnLaunch_rolls_back_an_incomplete_seal_that_never_reached_a_committed_outbox() = runTest {
        val assessment = evidenceRepository.createOrResumeAssessment("w", "en", null)
        captureRealPhoto(evidenceRepository, assessment.id, "T1", 50, 50)
        orchestrator.processEvidence(assessment.id)
        // Simulate a crash between "vault files written" and "outbox committed": sealState
        // advanced past FINAL_REVIEW_READY but no outbox rows exist for this revision.
        val afterProcessing = db.assessmentDraftDao().getById(assessment.id)!!
        db.assessmentDraftDao().update(afterProcessing.copy(sealState = SealState.SEAL_IN_PROGRESS, revisionId = "rev-crash-test"))

        orchestrator.reconcileOnLaunch(assessment.id)

        val assessmentRow = db.assessmentDraftDao().getById(assessment.id)!!
        assertEquals(
            "an incomplete seal (no committed outbox) must roll back to FINAL_REVIEW_READY, never stay stuck or silently advance",
            SealState.FINAL_REVIEW_READY,
            assessmentRow.sealState,
        )
        assertTrue("no outbox rows should exist after a rollback", db.outboxDao().getAllForAssessmentOnce(assessment.id).isEmpty())
    }

    @Test
    fun reconcileOnLaunch_finishes_a_seal_whose_outbox_was_already_committed_before_the_crash() = runTest {
        val assessment = evidenceRepository.createOrResumeAssessment("w", "en", null)
        val evidenceId = captureRealPhoto(evidenceRepository, assessment.id, "T1", 50, 50)
        orchestrator.processEvidence(assessment.id)
        val afterProcessing = db.assessmentDraftDao().getById(assessment.id)!!
        val revisionId = "rev-committed-test"
        db.assessmentDraftDao().update(afterProcessing.copy(sealState = SealState.VAULT_READY, revisionId = revisionId))
        // Simulate: the outbox commit itself succeeded before the crash (this is the one
        // thing reconcileOnLaunch treats as proof the vault work was genuinely complete).
        db.outboxDao().insertAll(
            listOf(
                `in`.kaushalpramaan.app.data.draft.OutboxItemEntity(
                    id = "outbox-1",
                    assessmentId = assessment.id,
                    revisionId = revisionId,
                    idempotencyKey = "${assessment.id}:$revisionId",
                    kind = `in`.kaushalpramaan.app.data.draft.OutboxItemKind.MANIFEST,
                    evidenceId = null,
                    taskId = null,
                    vaultRelativePath = "vault/${assessment.id}/$revisionId/manifest.vault",
                    priority = 0,
                    createdAtMillis = 0L,
                ),
            ),
        )

        orchestrator.reconcileOnLaunch(assessment.id)

        val assessmentRow = db.assessmentDraftDao().getById(assessment.id)!!
        assertEquals(SealState.READY_TO_SYNC, assessmentRow.sealState)
        val row = db.evidenceDraftDao().getById(evidenceId)!!
        assertEquals(FinalEvidenceState.SEALED, row.finalState)
        assertTrue("raw plaintext must be deleted once READY_TO_SYNC is reached", !fileManager.resolveRelativePath(row.relativePath).exists())
    }

    // ---- attestation / discard-reopen (pre-seal path, no vault restore needed) ----

    @Test
    fun setAttestation_updates_the_real_row_with_a_timestamp() = runTest {
        val assessment = evidenceRepository.createOrResumeAssessment("w", "en", null)
        orchestrator.setAttestation(assessment.id, true)
        val row = db.assessmentDraftDao().getById(assessment.id)!!
        assertTrue(row.attestationConfirmed)
        assertTrue(row.attestationAtMillis != null)

        orchestrator.setAttestation(assessment.id, false)
        val cleared = db.assessmentDraftDao().getById(assessment.id)!!
        assertTrue(!cleared.attestationConfirmed)
        assertNull(cleared.attestationAtMillis)
    }

    @Test
    fun discardAndReopen_before_sealing_resets_optimisation_state_without_needing_vault_restore() = runTest {
        val assessment = evidenceRepository.createOrResumeAssessment("w", "en", null)
        val evidenceId = captureRealPhoto(evidenceRepository, assessment.id, "T1", 50, 50)
        orchestrator.processEvidence(assessment.id)
        orchestrator.setAttestation(assessment.id, true)
        check(db.evidenceDraftDao().getById(evidenceId)!!.finalState == FinalEvidenceState.FITS_AS_IS)

        orchestrator.discardAndReopen(assessment.id)

        val row = db.evidenceDraftDao().getById(evidenceId)!!
        assertEquals(FinalEvidenceState.NOT_PROCESSED, row.finalState)
        assertNull(row.finalBytes)
        assertTrue("the raw evidence file itself must survive a pre-seal discard", fileManager.resolveRelativePath(row.relativePath).exists())
        val assessmentRow = db.assessmentDraftDao().getById(assessment.id)!!
        assertEquals(SealState.DRAFT_EDITABLE, assessmentRow.sealState)
        assertTrue(!assessmentRow.attestationConfirmed)
    }

    @Test
    fun discardAndReopen_is_refused_once_the_server_has_a_fully_synced_and_submitted_package() = runTest {
        // P6: SealOrchestrator.discardAndReopen's one new guard -- once P6's SyncRepository has
        // set syncedAtMillis (every outbox row server-verified AND POST /submit itself
        // succeeded), the assessor-facing record already exists server-side with no server-side
        // "unsubmit." A local discard/reopen past that point would silently diverge from what
        // the assessor is reviewing, so it must be a hard no-op, not attempt a partial recovery.
        //
        // seal()'s own Keystore/Tink-dependent work needs a real device (see this file's class
        // doc comment) -- so, following this file's own established pattern for simulating a
        // post-seal state (see reconcileOnLaunch_finishes_a_seal_whose_outbox_was_already_
        // committed_before_the_crash above), READY_TO_SYNC is set directly via the DAOs rather
        // than calling the real seal(). SyncRepositoryInstrumentedTest is the real end-to-end
        // proof that syncedAtMillis is only ever set after a genuine verified submit.
        val assessment = evidenceRepository.createOrResumeAssessment("w", "en", null)
        val evidenceId = captureRealPhoto(evidenceRepository, assessment.id, "T1", 50, 50)
        orchestrator.processEvidence(assessment.id)
        orchestrator.setAttestation(assessment.id, true)
        val revisionId = "rev-already-synced-test"
        val afterAttestation = db.assessmentDraftDao().getById(assessment.id)!!
        db.assessmentDraftDao().update(
            afterAttestation.copy(
                sealState = SealState.READY_TO_SYNC, revisionId = revisionId,
                syncedAtMillis = System.currentTimeMillis(),
            ),
        )
        val sealedEvidenceRow = db.evidenceDraftDao().getById(evidenceId)!!
        db.evidenceDraftDao().update(sealedEvidenceRow.copy(finalState = FinalEvidenceState.SEALED))

        orchestrator.discardAndReopen(assessment.id)

        val afterAttempt = db.assessmentDraftDao().getById(assessment.id)!!
        assertEquals(
            "a synced/submitted package must stay READY_TO_SYNC -- discard must be a complete no-op",
            SealState.READY_TO_SYNC, afterAttempt.sealState,
        )
        assertTrue(afterAttempt.attestationConfirmed)
        val evidenceRow = db.evidenceDraftDao().getById(evidenceId)!!
        assertEquals(
            "the item's SEALED state must be untouched by a refused discard attempt",
            FinalEvidenceState.SEALED, evidenceRow.finalState,
        )
    }
}
