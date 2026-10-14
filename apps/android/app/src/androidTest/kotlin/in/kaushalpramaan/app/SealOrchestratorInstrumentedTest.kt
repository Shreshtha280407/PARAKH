package `in`.kaushalpramaan.app

import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.data.draft.AppDatabase
import `in`.kaushalpramaan.app.data.draft.BeginCaptureResult
import `in`.kaushalpramaan.app.data.draft.EvidenceFileManager
import `in`.kaushalpramaan.app.data.draft.EvidenceRepository
import `in`.kaushalpramaan.app.data.draft.FinalEvidenceState
import `in`.kaushalpramaan.app.data.draft.FinalizeResult
import `in`.kaushalpramaan.app.data.draft.OutboxItemKind
import `in`.kaushalpramaan.app.data.draft.SealState
import `in`.kaushalpramaan.app.data.seal.ProcessOutcome
import `in`.kaushalpramaan.app.data.seal.SealOrchestrator
import `in`.kaushalpramaan.app.data.seal.SealOutcome
import `in`.kaushalpramaan.core.mapping.RulesLoader
import `in`.kaushalpramaan.core.seal.VaultKeysetProvider
import `in`.kaushalpramaan.core.seal.SealManifest
import `in`.kaushalpramaan.core.seal.SignedManifestPackage
import `in`.kaushalpramaan.core.seal.VaultStreamCipher
import android.util.Base64
import `in`.kaushalpramaan.media.PhotoOptimizer
import `in`.kaushalpramaan.media.VideoOptimizer
import android.graphics.Bitmap
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.io.FileOutputStream
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Real-device-only proof of the parts of the P5 seal pipeline that need a real Android
 * Keystore and real Tink StreamingAead (Robolectric has no real AndroidKeyStore provider --
 * see SealOrchestratorTest for everything reachable without one): a full real seal (real
 * Keystore ECDSA signature, real encrypted vault files, real committed outbox), tamper/AAD-
 * swap rejection against the real vault, and discard/reopen's real decrypt-to-restore path.
 */
@RunWith(AndroidJUnit4::class)
class SealOrchestratorInstrumentedTest {

    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    private fun freshHarness(): Triple<EvidenceRepository, SealOrchestrator, AppDatabase> {
        val dbName = "kp_seal_test_${System.nanoTime()}.db"
        val db = AppDatabase.build(context, dbName)
        val fileManager = EvidenceFileManager(context)
        val rules = RulesLoader.load()
        val repository = EvidenceRepository(db.assessmentDraftDao(), db.taskDraftDao(), db.evidenceDraftDao(), fileManager, rules)
        val orchestrator = SealOrchestrator(
            assessmentDraftDao = db.assessmentDraftDao(),
            evidenceDraftDao = db.evidenceDraftDao(),
            outboxDao = db.outboxDao(),
            fileManager = fileManager,
            rules = rules,
            photoOptimizer = PhotoOptimizer(),
            videoOptimizer = VideoOptimizer(context),
            vaultKeysetProvider = VaultKeysetProvider(context),
            appVersion = "instrumented-test",
            signingKeyAlias = "kp_seal_test_key_${System.nanoTime()}",
        )
        return Triple(repository, orchestrator, db)
    }

    private suspend fun captureRealPhoto(repo: EvidenceRepository, assessmentId: String, taskId: String): String {
        val begin = repo.beginCapture(assessmentId, taskId, EvidenceType.PHOTO, debugOverrideRequested = false)
        check(begin is BeginCaptureResult.Started)
        val bitmap = Bitmap.createBitmap(200, 150, Bitmap.Config.ARGB_8888)
        for (y in 0 until 150) for (x in 0 until 200) {
            bitmap.setPixel(x, y, (0xFF shl 24) or ((x * 255 / 200) shl 16) or ((y * 255 / 150) shl 8))
        }
        begin.stagingFile.parentFile?.mkdirs()
        FileOutputStream(begin.stagingFile).use { out -> bitmap.compress(Bitmap.CompressFormat.JPEG, 100, out) }
        bitmap.recycle()
        val result = repo.finalizeCapture(begin.evidenceId, success = true, widthPx = 200, heightPx = 150)
        check(result is FinalizeResult.Ready)
        return begin.evidenceId
    }

    @Test
    fun full_real_seal_produces_a_real_keystore_signature_and_a_real_encrypted_vault_with_committed_outbox() = runBlocking {
        val (repo, orchestrator, db) = freshHarness()
        try {
            val assessment = repo.createOrResumeAssessment("KP-SEAL-TEST", "en", null)
            val evidenceId = captureRealPhoto(repo, assessment.id, "T1")

            assertEquals(ProcessOutcome.AllFit, orchestrator.processEvidence(assessment.id))
            orchestrator.setAttestation(assessment.id, true)
            val sealOutcome = orchestrator.seal(assessment.id)

            assertEquals(SealOutcome.Sealed, sealOutcome)
            val sealedAssessment = db.assessmentDraftDao().getById(assessment.id)!!
            assertEquals(SealState.READY_TO_SYNC, sealedAssessment.sealState)
            assertTrue(sealedAssessment.signerPublicKeyBase64!!.isNotBlank())

            // Real outbox: manifest first (priority 0), then evidence.
            val outboxRows = db.outboxDao().getAllForAssessmentOnce(assessment.id)
            assertEquals(2, outboxRows.size)
            assertEquals(OutboxItemKind.MANIFEST, outboxRows[0].kind)
            assertEquals(0, outboxRows[0].priority)
            assertEquals(OutboxItemKind.EVIDENCE, outboxRows[1].kind)
            assertTrue(outboxRows[1].priority >= 1)

            // Real vault files exist and are NOT plaintext (no JPEG magic bytes, no raw pixel
            // header), proving real encryption happened, not a pass-through copy.
            val fileManager = EvidenceFileManager(context)
            for (row in outboxRows) {
                val vaultFile = fileManager.resolveRelativePath(row.vaultRelativePath)
                assertTrue("vault file must exist: ${row.vaultRelativePath}", vaultFile.exists())
                val header = vaultFile.inputStream().use { it.readNBytes(4) }
                val jpegMagic = byteArrayOf(0xFF.toByte(), 0xD8.toByte(), 0xFF.toByte())
                assertFalse(
                    "vault file must not start with a plaintext JPEG magic header",
                    header.size >= 3 && header[0] == jpegMagic[0] && header[1] == jpegMagic[1] && header[2] == jpegMagic[2],
                )
            }

            // Plaintext cleanup: raw capture and any optimisation temp must be gone.
            val sealedRow = db.evidenceDraftDao().getById(evidenceId)!!
            assertEquals(FinalEvidenceState.SEALED, sealedRow.finalState)
            // Sync (P6) reuses this persisted hash instead of re-hashing plaintext at upload
            // time -- if seal() ever stops writing it back, every real upload fails closed.
            assertEquals(64, sealedRow.finalSha256?.length)
            assertFalse(fileManager.resolveRelativePath(sealedRow.relativePath).exists())
            val tempDir = fileManager.optimizationTempDir(assessment.id, "T1")
            assertTrue("no plaintext optimisation temp should remain after a successful seal", tempDir.listFiles()?.isEmpty() != false)
        } finally {
            db.close()
        }
    }

    @Test
    fun tampering_with_a_copied_vault_file_breaks_decryption_associated_data_binding_holds() = runBlocking {
        val (repo, orchestrator, db) = freshHarness()
        try {
            val assessment = repo.createOrResumeAssessment("KP-SEAL-TEST", "en", null)
            captureRealPhoto(repo, assessment.id, "T1")
            orchestrator.processEvidence(assessment.id)
            orchestrator.setAttestation(assessment.id, true)
            check(orchestrator.seal(assessment.id) == SealOutcome.Sealed)

            val fileManager = EvidenceFileManager(context)
            val outboxRows = db.outboxDao().getAllForAssessmentOnce(assessment.id)
            val evidenceVaultFile = fileManager.resolveRelativePath(outboxRows.first { it.kind == OutboxItemKind.EVIDENCE }.vaultRelativePath)

            // Flip one byte in a COPY of the ciphertext and confirm Tink's own AEAD
            // authentication rejects it (real tamper-evidence, not just a hash comparison).
            val tamperedCopy = File(context.cacheDir, "tampered_${System.nanoTime()}.vault")
            val bytes = evidenceVaultFile.readBytes()
            bytes[bytes.size / 2] = (bytes[bytes.size / 2] + 1).toByte()
            tamperedCopy.writeBytes(bytes)

            val cipher = VaultKeysetProvider(context).getOrCreateCipher()
            val revisionId = db.assessmentDraftDao().getById(assessment.id)!!.revisionId!!
            val evidenceId = outboxRows.first { it.kind == OutboxItemKind.EVIDENCE }.evidenceId!!
            val decryptedOut = File(context.cacheDir, "should_not_decrypt_${System.nanoTime()}.jpg")
            var threw = false
            try {
                cipher.decryptFile(
                    tamperedCopy,
                    decryptedOut,
                    `in`.kaushalpramaan.core.seal.VaultStreamCipher.associatedData(assessment.id, revisionId, evidenceId, "evidence"),
                )
            } catch (_: Exception) {
                threw = true
            }
            assertTrue("decrypting a tampered vault copy must fail, never silently succeed", threw)
            tamperedCopy.delete()
            decryptedOut.delete()
            Unit
        } finally {
            db.close()
        }
    }

    @Test
    fun discard_and_reopen_after_a_real_seal_restores_evidence_by_decrypting_the_real_vault() = runBlocking {
        val (repo, orchestrator, db) = freshHarness()
        try {
            val assessment = repo.createOrResumeAssessment("KP-SEAL-TEST", "en", null)
            val evidenceId = captureRealPhoto(repo, assessment.id, "T1")
            val originalBytes = EvidenceFileManager(context).resolveRelativePath(
                db.evidenceDraftDao().getById(evidenceId)!!.relativePath,
            ).readBytes()

            orchestrator.processEvidence(assessment.id)
            orchestrator.setAttestation(assessment.id, true)
            check(orchestrator.seal(assessment.id) == SealOutcome.Sealed)
            val fileManager = EvidenceFileManager(context)
            check(!fileManager.resolveRelativePath(db.evidenceDraftDao().getById(evidenceId)!!.relativePath).exists())

            orchestrator.discardAndReopen(assessment.id)

            val restoredRow = db.evidenceDraftDao().getById(evidenceId)!!
            assertEquals(FinalEvidenceState.NOT_PROCESSED, restoredRow.finalState)
            val restoredFile = fileManager.resolveRelativePath(restoredRow.relativePath)
            assertTrue("the raw evidence file must be restored from the vault", restoredFile.exists())
            assertTrue("restored bytes must exactly match the original real capture", restoredFile.readBytes().contentEquals(originalBytes))
            val assessmentRow = db.assessmentDraftDao().getById(assessment.id)!!
            assertEquals(SealState.DRAFT_EDITABLE, assessmentRow.sealState)
            assertTrue(db.outboxDao().getAllForAssessmentOnce(assessment.id).isEmpty())
        } finally {
            db.close()
        }
    }

    @Test
    fun discard_and_reopen_after_a_seal_that_actually_optimised_restores_matching_metadata() = runBlocking {
        val (repo, orchestrator, db) = freshHarness()
        try {
            val assessment = repo.createOrResumeAssessment("KP-SEAL-TEST", "en", null)
            val evidenceId = captureRealPhoto(repo, assessment.id, "T1")
            val rawBytesBefore = db.evidenceDraftDao().getById(evidenceId)!!.byteSize

            // A forced budget well under the raw size (but not so tiny the quality floor can't
            // reach it) drives PhotoOptimizer down its real quality ladder so the vault ends up
            // holding genuinely smaller/recompressed bytes, not an untouched copy of the raw
            // capture -- the scenario the KeptAsIs-only test above never exercises, and the one
            // where a live device gate run found byteSize/widthPx/heightPx were left stale at
            // the original raw values after a real discard/reopen.
            val forcedBudget = rawBytesBefore / 2
            check(orchestrator.processEvidence(assessment.id, debugForcedTotalBudgetBytes = forcedBudget) == ProcessOutcome.AllFit)
            val processedRow = db.evidenceDraftDao().getById(evidenceId)!!
            check(processedRow.finalState == FinalEvidenceState.OPTIMIZED) { "test setup must actually compress, not just pass through" }
            val finalBytes = requireNotNull(processedRow.finalBytes)
            val finalWidthPx = requireNotNull(processedRow.finalWidthPx)
            val finalHeightPx = requireNotNull(processedRow.finalHeightPx)
            assertTrue("the forced budget must genuinely shrink the file for this test to be meaningful", finalBytes < rawBytesBefore)

            orchestrator.setAttestation(assessment.id, true)
            check(orchestrator.seal(assessment.id) == SealOutcome.Sealed)

            orchestrator.discardAndReopen(assessment.id)

            val restoredRow = db.evidenceDraftDao().getById(evidenceId)!!
            val fileManager = EvidenceFileManager(context)
            val restoredFile = fileManager.resolveRelativePath(restoredRow.relativePath)
            assertEquals("DB byteSize must match what the vault actually restored, not the stale pre-seal raw size", finalBytes, restoredFile.length())
            assertEquals(finalBytes, restoredRow.byteSize)
            assertEquals(finalWidthPx, restoredRow.widthPx)
            assertEquals(finalHeightPx, restoredRow.heightPx)
        } finally {
            db.close()
        }
    }

    @Test
    fun seal_without_attestation_is_rejected_and_nothing_is_written_to_the_vault() = runBlocking {
        val (repo, orchestrator, db) = freshHarness()
        try {
            val assessment = repo.createOrResumeAssessment("KP-SEAL-TEST", "en", null)
            captureRealPhoto(repo, assessment.id, "T1")
            orchestrator.processEvidence(assessment.id)

            val outcome = orchestrator.seal(assessment.id)

            assertEquals(SealOutcome.AttestationRequired, outcome)
            assertEquals(SealState.FINAL_REVIEW_READY, db.assessmentDraftDao().getById(assessment.id)!!.sealState)
            assertTrue(db.outboxDao().getAllForAssessmentOnce(assessment.id).isEmpty())
        } finally {
            db.close()
        }
    }

    // ---- P7: task-specific reassessment -- sealTargetedRevision ----

    @Test
    fun targeted_revision_reuses_unchanged_tasks_by_reference_and_only_vault_encrypts_the_reopened_task() = runBlocking {
        val (repo, orchestrator, db) = freshHarness()
        try {
            val assessment = repo.createOrResumeAssessment("KP-SEAL-TEST", "en", null)
            val v1EvidenceIds = RulesLoader.load().tasksFile.tasks.associate { it.id to captureRealPhoto(repo, assessment.id, it.id) }
            check(orchestrator.processEvidence(assessment.id) == ProcessOutcome.AllFit)
            orchestrator.setAttestation(assessment.id, true)
            check(orchestrator.seal(assessment.id) == SealOutcome.Sealed)
            val v1Revision = db.assessmentDraftDao().getById(assessment.id)!!.revisionId!!
            val v1Sha256ByTask = v1EvidenceIds.mapValues { (_, id) -> db.evidenceDraftDao().getById(id)!!.finalSha256!! }

            // A fresh T4 capture -- the only task being reopened.
            val newT4EvidenceId = captureRealPhoto(repo, assessment.id, "T4")
            check(orchestrator.processEvidence(assessment.id) == ProcessOutcome.AllFit)
            orchestrator.setAttestation(assessment.id, true)

            val outcome = orchestrator.sealTargetedRevision(assessment.id, setOf("T4"))

            assertEquals(SealOutcome.Sealed, outcome)
            val v2Assessment = db.assessmentDraftDao().getById(assessment.id)!!
            assertEquals(SealState.READY_TO_SYNC, v2Assessment.sealState)
            assertNull("a fresh revision must actually attempt to sync", v2Assessment.syncedAtMillis)
            val v2Revision = v2Assessment.revisionId!!
            assertTrue("a targeted revision must mint a genuinely new revisionId", v2Revision != v1Revision)

            // Only ONE new outbox row set is committed: the v2 manifest + the ONE new T4
            // evidence item -- never a row for the four unchanged tasks.
            val outboxRows = db.outboxDao().getAllForAssessmentOnce(assessment.id).filter { it.revisionId == v2Revision }
            assertEquals(2, outboxRows.size)
            assertEquals(OutboxItemKind.MANIFEST, outboxRows[0].kind)
            assertEquals(OutboxItemKind.EVIDENCE, outboxRows[1].kind)
            assertEquals(newT4EvidenceId, outboxRows[1].evidenceId)
            val newT4 = db.evidenceDraftDao().getById(newT4EvidenceId)!!
            assertEquals("reassessment sealing must preserve the new item's receipt metadata", 64, newT4.finalSha256?.length)
            assertTrue(EvidenceFileManager(context).resolveRelativePath(requireNotNull(newT4.vaultRelativePath)).isFile)

            // The OLD T4 item is now historical -- immutable, excluded from the active set.
            val oldT4 = db.evidenceDraftDao().getById(v1EvidenceIds.getValue("T4"))!!
            assertTrue(oldT4.fromPreviousRevision)
            assertEquals(FinalEvidenceState.SEALED, oldT4.finalState)

            // Every OTHER task's v1 item is untouched -- same finalSha256, not marked
            // historical, and (critically) its vault file was never re-touched by the v2
            // seal, since it had none left to re-touch (P6 already deleted it post-receipt
            // in reality; here it simply proves sealTargetedRevision never tries).
            for (task in listOf("T1", "T2", "T3", "T5")) {
                val item = db.evidenceDraftDao().getById(v1EvidenceIds.getValue(task))!!
                assertFalse("unchanged task '$task' must not be marked historical", item.fromPreviousRevision)
                assertEquals(v1Sha256ByTask.getValue(task), item.finalSha256)
            }
        } finally {
            db.close()
        }
    }

    @Test
    fun repeated_targeted_revisions_inherit_only_active_evidence_after_receipt_cleanup() = runBlocking {
        val (repo, orchestrator, db) = freshHarness()
        try {
            val assessment = repo.createOrResumeAssessment("KP-SEAL-TEST", "en", null)
            captureRealPhoto(repo, assessment.id, "T1")
            captureRealPhoto(repo, assessment.id, "T2")
            check(orchestrator.processEvidence(assessment.id) == ProcessOutcome.AllFit)
            orchestrator.setAttestation(assessment.id, true)
            check(orchestrator.seal(assessment.id) == SealOutcome.Sealed)
            val fileManager = EvidenceFileManager(context)

            suspend fun receiptAndReopen() {
                fileManager.deleteVaultTree(assessment.id)
                db.outboxDao().deleteAllForAssessment(assessment.id)
                val current = db.assessmentDraftDao().getById(assessment.id)!!
                db.assessmentDraftDao().update(current.copy(sealState = SealState.DRAFT_EDITABLE, syncedAtMillis = System.currentTimeMillis()))
            }

            receiptAndReopen()
            val activeT1 = captureRealPhoto(repo, assessment.id, "T1")
            check(orchestrator.processEvidence(assessment.id) == ProcessOutcome.AllFit)
            orchestrator.setAttestation(assessment.id, true)
            check(orchestrator.sealTargetedRevision(assessment.id, setOf("T1")) == SealOutcome.Sealed)

            receiptAndReopen()
            val activeT2 = captureRealPhoto(repo, assessment.id, "T2")
            check(orchestrator.processEvidence(assessment.id) == ProcessOutcome.AllFit)
            orchestrator.setAttestation(assessment.id, true)
            assertEquals(SealOutcome.Sealed, orchestrator.sealTargetedRevision(assessment.id, setOf("T2")))

            val latest = db.assessmentDraftDao().getById(assessment.id)!!
            val vault = fileManager.resolveRelativePath(requireNotNull(latest.manifestVaultRelativePath))
            val cipher = VaultKeysetProvider(context).getOrCreateCipher()
            val envelope = cipher.openDecryptingStream(vault, VaultStreamCipher.associatedData(assessment.id, latest.revisionId!!, "manifest", "manifest")).use { it.readBytes() }
            val signed = SignedManifestPackage.fromJsonBytes(envelope)
            val canonical = Base64.decode(signed.manifestBase64, Base64.NO_WRAP)
            val manifest = SealManifest.CANONICAL_JSON.decodeFromString(SealManifest.serializer(), canonical.decodeToString())
            assertEquals("superseded evidence must never re-enter the current snapshot", setOf(activeT1, activeT2), manifest.evidence.map { it.evidenceId }.toSet())
            assertEquals("INHERITED", manifest.evidence.single { it.evidenceId == activeT1 }.processing)
            val outbox = db.outboxDao().getAllForAssessmentOnce(assessment.id)
            assertEquals(2, outbox.size)
            assertEquals(activeT2, outbox.single { it.kind == OutboxItemKind.EVIDENCE }.evidenceId)
        } finally {
            db.close()
        }
    }

    @Test
    fun targeted_revision_fails_closed_when_the_reopened_task_has_no_new_evidence() = runBlocking {
        val (repo, orchestrator, db) = freshHarness()
        try {
            val assessment = repo.createOrResumeAssessment("KP-SEAL-TEST", "en", null)
            captureRealPhoto(repo, assessment.id, "T1")
            check(orchestrator.processEvidence(assessment.id) == ProcessOutcome.AllFit)
            orchestrator.setAttestation(assessment.id, true)
            check(orchestrator.seal(assessment.id) == SealOutcome.Sealed)

            // Nothing new captured for T4 -- it is being "reopened" but the worker hasn't
            // actually added anything yet.
            val originalRevision = db.assessmentDraftDao().getById(assessment.id)!!.revisionId
            val originalOutbox = db.outboxDao().getAllForAssessmentOnce(assessment.id)
            assertEquals(SealOutcome.NotReady, orchestrator.sealTargetedRevision(assessment.id, setOf("T4")))

            // The real UI runs optimisation and requires a fresh attestation before
            // calling this method. Reach that state without adding any new evidence,
            // so the test exercises the missing-evidence guard rather than readiness.
            check(orchestrator.processEvidence(assessment.id) == ProcessOutcome.AllFit)
            orchestrator.setAttestation(assessment.id, true)
            val outcome = orchestrator.sealTargetedRevision(assessment.id, setOf("T4"))

            assertEquals(SealOutcome.NoEvidence, outcome)
            assertEquals(originalRevision, db.assessmentDraftDao().getById(assessment.id)!!.revisionId)
            assertEquals(originalOutbox, db.outboxDao().getAllForAssessmentOnce(assessment.id))
        } finally {
            db.close()
        }
    }
}
