package `in`.kaushalpramaan.app.data.seal

import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.data.draft.AssessmentDraftDao
import `in`.kaushalpramaan.app.data.draft.AssessmentDraftEntity
import `in`.kaushalpramaan.app.data.draft.DRAFT_JSON
import `in`.kaushalpramaan.app.data.draft.EvidenceDraftDao
import `in`.kaushalpramaan.app.data.draft.EvidenceDraftEntity
import `in`.kaushalpramaan.app.data.draft.EvidenceDraftState
import `in`.kaushalpramaan.app.data.draft.EvidenceFileManager
import `in`.kaushalpramaan.app.data.draft.FinalEvidenceState
import `in`.kaushalpramaan.app.data.draft.OutboxDao
import `in`.kaushalpramaan.app.data.draft.OutboxItemEntity
import `in`.kaushalpramaan.app.data.draft.OutboxItemKind
import `in`.kaushalpramaan.app.data.draft.SealState
import `in`.kaushalpramaan.core.budget.BudgetLedger
import `in`.kaushalpramaan.core.budget.LedgerItem
import `in`.kaushalpramaan.core.budget.TaskBudget
import `in`.kaushalpramaan.core.mapping.MatchOutput
import `in`.kaushalpramaan.core.mapping.Rules
import `in`.kaushalpramaan.core.seal.ManifestDeclarationSummary
import `in`.kaushalpramaan.core.seal.ManifestEvidenceItem
import `in`.kaushalpramaan.core.seal.ManifestSigner
import `in`.kaushalpramaan.core.seal.ManifestTaskTotal
import `in`.kaushalpramaan.core.seal.SealManifest
import `in`.kaushalpramaan.core.seal.SignedManifestPackage
import `in`.kaushalpramaan.core.seal.StreamingHasher
import `in`.kaushalpramaan.core.seal.VaultKeysetProvider
import `in`.kaushalpramaan.core.seal.VaultStreamCipher
import `in`.kaushalpramaan.core.seal.VaultCipher
import kotlinx.serialization.decodeFromString
import `in`.kaushalpramaan.media.PhotoOptimizationResult
import `in`.kaushalpramaan.media.PhotoOptimizer
import `in`.kaushalpramaan.media.VideoOptimizationResult
import `in`.kaushalpramaan.media.VideoOptimizer
import android.util.Base64
import android.util.Log
import java.io.File
import java.util.UUID

private const val LOG_TAG = "KP-Seal"

sealed class ProcessOutcome {
    data object AllFit : ProcessOutcome()
    data object SomeItemsExceedBudget : ProcessOutcome()
    data object NoReadyEvidence : ProcessOutcome()
    data object NoActiveAssessment : ProcessOutcome()
}

sealed class SealOutcome {
    data object Sealed : SealOutcome()
    data object NotReady : SealOutcome()
    data object AttestationRequired : SealOutcome()
    data object ItemsNotReady : SealOutcome()
    data object NoEvidence : SealOutcome()
    data object VerificationFailed : SealOutcome()
    data object NoActiveAssessment : SealOutcome()
}

/**
 * Orchestrates P5's automatic optimisation + budget enforcement + canonical manifest +
 * signing + encrypted vault + outbox pipeline (spec parts B-G) on top of the three pure/
 * Android-library modules (`core:budget`, `media`, `core:seal`) and the P4 draft Room schema.
 * This is the one place that ties them together and owns the [SealState] state machine's
 * crash-safe transitions.
 */
class SealOrchestrator(
    private val assessmentDraftDao: AssessmentDraftDao,
    private val evidenceDraftDao: EvidenceDraftDao,
    private val outboxDao: OutboxDao,
    private val fileManager: EvidenceFileManager,
    private val rules: Rules,
    private val photoOptimizer: PhotoOptimizer,
    private val videoOptimizer: VideoOptimizer,
    private val vaultKeysetProvider: VaultKeysetProvider,
    private val appVersion: String,
    private val signingKeyAlias: String = "kp_seal_signing_key",
) {
    /** [debugForcedTotalBudgetBytes] is the debug-only `P5_TEST_ONLY` virtual-remaining-budget
     * override (spec part D.6): routed through this exact same production ledger
     * construction, never a separate mock path -- it only ever substitutes a smaller total
     * budget number, real per-task budgets and real optimisers are unchanged. Null (always
     * the case in release builds; see BuildConfig.P5_TEST_ONLY_FORCE_OPTIMIZE_ENABLED) uses
     * the real configured total. */
    private fun ledgerFor(debugForcedTotalBudgetBytes: Long?) = BudgetLedger(
        rules.tasksFile.tasks.map { TaskBudget(it.id, it.budgetBytes) },
        debugForcedTotalBudgetBytes ?: rules.tasksFile.finalEvidenceBudgetBytes,
    )

    /** Call once per process start, before showing any P5 UI for a resumed assessment.
     * Resumes interrupted PROCESSING (idempotent, per-item), and safely rolls back an
     * interrupted SEAL_IN_PROGRESS/VAULT_READY attempt that never reached a committed outbox
     * -- never exposes a partially encrypted package as READY_TO_SYNC. */
    suspend fun reconcileOnLaunch(assessmentId: String) {
        val assessment = assessmentDraftDao.getById(assessmentId) ?: return
        when (assessment.sealState) {
            SealState.PROCESSING -> {
                Log.d(LOG_TAG, "reconcile result=resuming_processing")
                processEvidence(assessmentId)
            }
            SealState.SEAL_IN_PROGRESS, SealState.VAULT_READY -> {
                val revisionId = assessment.revisionId
                val committedOutbox = revisionId != null &&
                    outboxDao.getAllForAssessmentOnce(assessmentId).any { it.revisionId == revisionId }
                if (committedOutbox) {
                    Log.d(LOG_TAG, "reconcile result=finishing_committed_seal")
                    finishSealAfterOutboxCommitted(assessmentId)
                } else {
                    Log.w(LOG_TAG, "reconcile result=rolling_back_incomplete_seal")
                    fileManager.deleteVaultTree(assessmentId)
                    assessmentDraftDao.getById(assessmentId)?.let {
                        assessmentDraftDao.update(it.copy(sealState = SealState.FINAL_REVIEW_READY))
                    }
                }
            }
            // Only READY_TO_SYNC legitimately owns vault/outbox rows. A crash mid-discardAndReopen
            // (or mid-seal before SEAL_IN_PROGRESS was ever persisted) can leave either behind
            // for an assessment that is genuinely not sealed; sweeping them here unconditionally
            // is always safe (both deletes are no-ops when nothing exists) and is what makes
            // discardAndReopen's own ordering crash-safe rather than merely crash-reduced.
            SealState.DRAFT_EDITABLE, SealState.FINAL_REVIEW_READY -> {
                outboxDao.deleteAllForAssessment(assessmentId)
                fileManager.deleteVaultTree(assessmentId)
            }
            // A genuinely sealed assessment never has plaintext on disk (spec G.5) -- if an
            // item's plaintext file exists here, the only way that happens is a process death
            // partway through discardAndReopen's restore-then-finish: the decrypt loop writes
            // real files with no DB write of its own (see finishDiscardAfterRestore), so a
            // crash right after it leaves plaintext restored, the vault still intact, and this
            // row still claiming READY_TO_SYNC. Finish what the user already asked for instead
            // of leaving an unencrypted duplicate of sealed evidence sitting on disk forever.
            SealState.READY_TO_SYNC -> {
                val items = evidenceDraftDao.getAllForAssessmentOnce(assessmentId).filter { it.state == EvidenceDraftState.READY }
                val crashedMidDiscard = items.any { fileManager.resolveRelativePath(it.relativePath).exists() }
                if (crashedMidDiscard) {
                    Log.w(LOG_TAG, "reconcile result=finishing_interrupted_discard")
                    finishDiscardAfterRestore(assessmentId, assessment, items)
                }
            }
        }
    }

    /** Runs the automatic photo/video optimisation pass (spec parts C/D) over every READY
     * evidence item not yet processed. Deterministic order (task id, then capture time) so
     * earlier items get first claim on the shrinking available budget as later items are
     * considered -- always recomputed from the real current item set, never a cached total. */
    suspend fun processEvidence(assessmentId: String, debugForcedTotalBudgetBytes: Long? = null): ProcessOutcome {
        val assessment = assessmentDraftDao.getById(assessmentId) ?: return ProcessOutcome.NoActiveAssessment
        val readyItems = evidenceDraftDao.getAllForAssessmentOnce(assessmentId).filter { it.state == EvidenceDraftState.READY }
        if (readyItems.isEmpty()) return ProcessOutcome.NoReadyEvidence
        val ledger = ledgerFor(debugForcedTotalBudgetBytes)

        assessmentDraftDao.update(assessment.copy(sealState = SealState.PROCESSING))

        val ordered = readyItems.sortedWith(compareBy({ it.taskId }, { it.createdAtMillis }))
        var anyFloorExceeded = false

        for (item in ordered) {
            if (item.finalState != FinalEvidenceState.NOT_PROCESSED) {
                if (item.finalState == FinalEvidenceState.QUALITY_FLOOR_EXCEEDED) anyFloorExceeded = true
                continue
            }
            // Only items that have ALREADY SUCCESSFULLY fit (FITS_AS_IS/OPTIMIZED, processed
            // earlier in this same pass or a prior resumed run) count as "used" here:
            //  - A NOT_PROCESSED sibling has claimed nothing yet -- counting its raw,
            //    pre-optimisation bytes would double-penalize this item for space its sibling
            //    hasn't even tried to shrink into yet, wrongly zeroing out its allowance.
            //  - A QUALITY_FLOOR_EXCEEDED sibling has already failed and blocks sealing
            //    regardless (the worker must retake/replace/remove it before a real seal);
            //    counting its floor-attempt bytes against the budget would needlessly
            //    cascade that one failure into every other item too, instead of giving each
            //    item an independent, fair shot at whatever was genuinely, successfully
            //    claimed so far.
            // Each item in the stable processing order gets whatever the budget has left
            // after everything that successfully fit so far -- not after everything that
            // merely exists or merely attempted and failed.
            val others = evidenceDraftDao.getAllForAssessmentOnce(assessmentId)
                .filter {
                    it.state == EvidenceDraftState.READY && it.id != item.id &&
                        (it.finalState == FinalEvidenceState.FITS_AS_IS || it.finalState == FinalEvidenceState.OPTIMIZED)
                }
                .map { LedgerItem(it.id, it.taskId, requireNotNull(it.finalBytes)) }
            val allowedBytes = ledger.allowedBytesFor(others, item.taskId)

            val updated = processOneItem(assessmentId, item, allowedBytes)
            evidenceDraftDao.update(updated)
            if (updated.finalState == FinalEvidenceState.QUALITY_FLOOR_EXCEEDED) anyFloorExceeded = true
            Log.d(LOG_TAG, "process_item task=${item.taskId} kind=${item.kind} result=${updated.finalState}")
        }

        val newSealState = if (anyFloorExceeded) SealState.DRAFT_EDITABLE else SealState.FINAL_REVIEW_READY
        assessmentDraftDao.getById(assessmentId)?.let { assessmentDraftDao.update(it.copy(sealState = newSealState)) }
        return if (anyFloorExceeded) ProcessOutcome.SomeItemsExceedBudget else ProcessOutcome.AllFit
    }

    private suspend fun processOneItem(assessmentId: String, item: EvidenceDraftEntity, allowedBytes: Long): EvidenceDraftEntity {
        val rawFile = fileManager.resolveRelativePath(item.relativePath)
        val tempDir = fileManager.optimizationTempDir(assessmentId, item.taskId)

        return if (item.kind == EvidenceType.PHOTO) {
            when (val result = photoOptimizer.optimize(rawFile, allowedBytes, tempDir)) {
                is PhotoOptimizationResult.KeptAsIs -> item.copy(
                    finalState = FinalEvidenceState.FITS_AS_IS,
                    finalRelativePath = item.relativePath,
                    finalBytes = result.bytes,
                    finalMimeType = "image/jpeg",
                    finalWidthPx = item.widthPx,
                    finalHeightPx = item.heightPx,
                )
                is PhotoOptimizationResult.Optimized -> item.copy(
                    finalState = FinalEvidenceState.OPTIMIZED,
                    finalRelativePath = fileManager.relativePathOf(result.file),
                    finalBytes = result.bytes,
                    finalMimeType = "image/jpeg",
                    finalWidthPx = result.widthPx,
                    finalHeightPx = result.heightPx,
                )
                is PhotoOptimizationResult.QualityFloorExceeded -> item.copy(
                    finalState = FinalEvidenceState.QUALITY_FLOOR_EXCEEDED,
                    finalRelativePath = fileManager.relativePathOf(result.bestAttemptFile),
                    finalBytes = result.bestAttemptBytes,
                    finalMimeType = "image/jpeg",
                )
                PhotoOptimizationResult.UndecodablePhoto -> item.copy(finalState = FinalEvidenceState.QUALITY_FLOOR_EXCEEDED)
            }
        } else {
            when (val result = videoOptimizer.optimize(rawFile, allowedBytes, tempDir)) {
                is VideoOptimizationResult.KeptAsIs -> item.copy(
                    finalState = FinalEvidenceState.FITS_AS_IS,
                    finalRelativePath = item.relativePath,
                    finalBytes = result.bytes,
                    finalMimeType = "video/mp4",
                    finalWidthPx = item.widthPx,
                    finalHeightPx = item.heightPx,
                    finalDurationMillis = item.durationMillis,
                )
                is VideoOptimizationResult.Optimized -> item.copy(
                    finalState = FinalEvidenceState.OPTIMIZED,
                    finalRelativePath = fileManager.relativePathOf(result.file),
                    finalBytes = result.bytes,
                    finalMimeType = "video/mp4",
                    finalWidthPx = result.widthPx,
                    finalHeightPx = result.heightPx,
                    finalDurationMillis = result.durationMillis,
                )
                is VideoOptimizationResult.QualityFloorExceeded -> item.copy(
                    finalState = FinalEvidenceState.QUALITY_FLOOR_EXCEEDED,
                    finalRelativePath = fileManager.relativePathOf(result.bestAttemptFile),
                    finalBytes = result.bestAttemptBytes,
                    finalMimeType = "video/mp4",
                )
                VideoOptimizationResult.InvalidContainer -> item.copy(finalState = FinalEvidenceState.QUALITY_FLOOR_EXCEEDED)
            }
        }
    }

    /** Minimal offline video trim (spec part D.5): re-validates and re-optimises through the
     * exact same pipeline as any other capture -- trimming never bypasses budget enforcement.
     * The existing evidence is left completely untouched unless the trim genuinely succeeds. */
    suspend fun trimVideo(assessmentId: String, evidenceId: String, startMs: Long, endMs: Long): Boolean {
        val item = evidenceDraftDao.getById(evidenceId) ?: return false
        if (item.kind != EvidenceType.VIDEO || item.state != EvidenceDraftState.READY) return false

        val sourceFile = fileManager.resolveRelativePath(item.relativePath)
        val tempDir = fileManager.optimizationTempDir(assessmentId, item.taskId)
        val trimmed = videoOptimizer.trim(sourceFile, startMs, endMs, tempDir) ?: return false
        val trimmedInfo = videoOptimizer.validateContainer(trimmed) ?: return false

        sourceFile.delete()
        item.finalRelativePath?.let { if (it != item.relativePath) fileManager.resolveRelativePath(it).delete() }

        evidenceDraftDao.update(
            item.copy(
                relativePath = fileManager.relativePathOf(trimmed),
                byteSize = trimmedInfo.bytes,
                durationMillis = trimmedInfo.durationMs,
                widthPx = trimmedInfo.widthPx,
                heightPx = trimmedInfo.heightPx,
                finalState = FinalEvidenceState.NOT_PROCESSED,
                finalRelativePath = null,
                finalBytes = null,
                finalSha256 = null,
                finalMimeType = null,
                finalWidthPx = null,
                finalHeightPx = null,
                finalDurationMillis = null,
                vaultRelativePath = null,
            ),
        )
        // The trimmed clip needs a fresh optimisation pass; any prior "ready to seal"
        // conclusion is now stale.
        assessmentDraftDao.getById(assessmentId)?.let {
            if (it.sealState == SealState.FINAL_REVIEW_READY) assessmentDraftDao.update(it.copy(sealState = SealState.DRAFT_EDITABLE))
        }
        Log.d(LOG_TAG, "trim_video task=${item.taskId} result=success newBytes=${trimmedInfo.bytes}")
        return true
    }

    /** Call after any evidence mutation that happens while editable (new capture started,
     * delete, replace) -- a prior "every item fits, ready to review" conclusion
     * (FINAL_REVIEW_READY) is stale the moment the evidence set changes, so this reverts to
     * DRAFT_EDITABLE, forcing a fresh `processEvidence()`/re-attestation before the worker
     * can seal again. A no-op for every other state (DRAFT_EDITABLE already, or a seal is
     * genuinely in progress/complete and evidence mutation is blocked in the UI by then
     * anyway -- see [in.kaushalpramaan.app.data.isEditable]). */
    suspend fun invalidateFinalReviewIfNeeded(assessmentId: String) {
        val assessment = assessmentDraftDao.getById(assessmentId) ?: return
        if (assessment.sealState == SealState.FINAL_REVIEW_READY) {
            assessmentDraftDao.update(assessment.copy(sealState = SealState.DRAFT_EDITABLE, attestationConfirmed = false, attestationAtMillis = null))
            Log.d(LOG_TAG, "invalidate_final_review result=reverted_to_draft_editable")
        }
    }

    suspend fun setAttestation(assessmentId: String, confirmed: Boolean) {
        val assessment = assessmentDraftDao.getById(assessmentId) ?: return
        assessmentDraftDao.update(
            assessment.copy(
                attestationConfirmed = confirmed,
                attestationAtMillis = if (confirmed) System.currentTimeMillis() else null,
            ),
        )
    }

    /** Builds the canonical manifest, signs it with the non-exportable Keystore EC key,
     * streams every final item (plus the signed manifest package) into the Tink-encrypted
     * vault with assessment/revision/evidence-bound associated data, commits the outbox rows,
     * and only then deletes plaintext raw/optimisation-temp files (spec part G.5). */
    suspend fun seal(assessmentId: String): SealOutcome {
        val assessment = assessmentDraftDao.getById(assessmentId) ?: return SealOutcome.NoActiveAssessment
        if (assessment.sealState != SealState.FINAL_REVIEW_READY) return SealOutcome.NotReady
        if (!assessment.attestationConfirmed) return SealOutcome.AttestationRequired

        val items = evidenceDraftDao.getAllForAssessmentOnce(assessmentId).filter { it.state == EvidenceDraftState.READY }
        if (items.isEmpty()) return SealOutcome.NoEvidence
        if (items.any { it.finalState == FinalEvidenceState.NOT_PROCESSED || it.finalState == FinalEvidenceState.QUALITY_FLOOR_EXCEEDED }) {
            return SealOutcome.ItemsNotReady
        }

        val revisionId = assessment.revisionId ?: UUID.randomUUID().toString()
        assessmentDraftDao.update(assessment.copy(sealState = SealState.SEAL_IN_PROGRESS, revisionId = revisionId))
        Log.d(LOG_TAG, "seal result=started revisionId=$revisionId items=${items.size}")

        val signingKey = ManifestSigner.getOrCreateSigningKey(signingKeyAlias)
        val publicKeyBase64 = Base64.encodeToString(signingKey.certificate.publicKey.encoded, Base64.NO_WRAP)
        val idempotencyKey = "$assessmentId:$revisionId"
        val now = System.currentTimeMillis()

        val sha256ByEvidenceId = mutableMapOf<String, String>()
        val manifestItems = items.map { item ->
            val finalFile = fileManager.resolveRelativePath(requireNotNull(item.finalRelativePath))
            val sha256 = StreamingHasher.sha256Hex(finalFile)
            sha256ByEvidenceId[item.id] = sha256
            ManifestEvidenceItem(
                evidenceId = item.id,
                taskId = item.taskId,
                kind = item.kind.name,
                fileName = finalFile.name,
                bytes = requireNotNull(item.finalBytes),
                sha256 = sha256,
                mimeType = item.finalMimeType ?: "application/octet-stream",
                durationMillis = item.finalDurationMillis,
                widthPx = item.finalWidthPx,
                heightPx = item.finalHeightPx,
                processing = item.finalState.name,
                capturedAtMillis = item.createdAtMillis,
            )
        }
        val taskTotals = rules.tasksFile.tasks.map { task ->
            ManifestTaskTotal(task.id, manifestItems.filter { it.taskId == task.id }.sumOf { it.bytes }, task.budgetBytes)
        }
        val manifest = SealManifest(
            schemaVersion = 1,
            assessmentId = assessmentId,
            revisionId = revisionId,
            qpCode = assessment.qpCode,
            qpVersion = assessment.qpVersion,
            appVersion = appVersion,
            createdAtMillis = assessment.createdAtMillis,
            sealedAtMillis = now,
            attestationConfirmed = true,
            attestationAtMillis = assessment.attestationAtMillis ?: now,
            evidence = manifestItems,
            taskTotals = taskTotals,
            assessmentFinalBytes = manifestItems.sumOf { it.bytes },
            assessmentBudgetBytes = rules.tasksFile.finalEvidenceBudgetBytes,
            idempotencyKey = idempotencyKey,
            signerKeyId = signingKeyAlias,
            signerPublicKeyBase64 = publicKeyBase64,
            declarationSummary = buildDeclarationSummary(assessment),
        )
        val canonicalBytes = manifest.canonicalJsonBytes()
        val signature = ManifestSigner.sign(canonicalBytes, signingKey.privateKey)
        if (!ManifestSigner.verify(canonicalBytes, signature, signingKey.certificate.publicKey)) {
            // Unreachable in practice (we just signed it with the matching key) -- fail
            // closed rather than ever persist an unverifiable package.
            Log.e(LOG_TAG, "seal result=failed category=self_verification_failed")
            assessmentDraftDao.getById(assessmentId)?.let { assessmentDraftDao.update(it.copy(sealState = SealState.FINAL_REVIEW_READY)) }
            return SealOutcome.VerificationFailed
        }

        val signedPackage = SignedManifestPackage(
            manifestBase64 = Base64.encodeToString(canonicalBytes, Base64.NO_WRAP),
            signatureBase64 = Base64.encodeToString(signature, Base64.NO_WRAP),
            algorithm = ManifestSigner.SIGNATURE_ALGORITHM,
            signerKeyId = signingKeyAlias,
            signerPublicKeyBase64 = publicKeyBase64,
        )
        val manifestPlainFile = File(fileManager.sealTempDir(assessmentId), "manifest_package.json")
        manifestPlainFile.writeBytes(signedPackage.toJsonBytes())

        val vaultDir = fileManager.vaultDir(assessmentId, revisionId)
        val cipher = vaultKeysetProvider.getOrCreateCipher()

        val manifestVaultFile = File(vaultDir, "manifest.vault")
        cipher.encryptFile(
            manifestPlainFile,
            manifestVaultFile,
            VaultStreamCipher.associatedData(assessmentId, revisionId, "manifest", "manifest"),
        )

        val vaultFilesByEvidenceId = mutableMapOf<String, File>()
        for (item in items) {
            val finalFile = fileManager.resolveRelativePath(requireNotNull(item.finalRelativePath))
            val vaultFile = File(vaultDir, "${item.id}.vault")
            cipher.encryptFile(
                finalFile,
                vaultFile,
                VaultStreamCipher.associatedData(assessmentId, revisionId, item.id, "evidence"),
            )
            vaultFilesByEvidenceId[item.id] = vaultFile
            evidenceDraftDao.update(
                item.copy(
                    vaultRelativePath = fileManager.relativePathOf(vaultFile),
                    finalSha256 = sha256ByEvidenceId[item.id],
                ),
            )
        }

        assessmentDraftDao.getById(assessmentId)?.let {
            assessmentDraftDao.update(
                it.copy(
                    sealState = SealState.VAULT_READY,
                    manifestVaultRelativePath = fileManager.relativePathOf(manifestVaultFile),
                    signerKeyId = signingKeyAlias,
                    signerPublicKeyBase64 = publicKeyBase64,
                    idempotencyKey = idempotencyKey,
                ),
            )
        }
        Log.d(LOG_TAG, "seal result=vault_ready revisionId=$revisionId")

        val outboxRows = mutableListOf(
            OutboxItemEntity(
                id = UUID.randomUUID().toString(),
                assessmentId = assessmentId,
                revisionId = revisionId,
                idempotencyKey = idempotencyKey,
                kind = OutboxItemKind.MANIFEST,
                evidenceId = null,
                taskId = null,
                vaultRelativePath = fileManager.relativePathOf(manifestVaultFile),
                priority = 0,
                createdAtMillis = now,
            ),
        )
        items.forEachIndexed { index, item ->
            outboxRows += OutboxItemEntity(
                id = UUID.randomUUID().toString(),
                assessmentId = assessmentId,
                revisionId = revisionId,
                idempotencyKey = idempotencyKey,
                kind = OutboxItemKind.EVIDENCE,
                evidenceId = item.id,
                taskId = item.taskId,
                vaultRelativePath = fileManager.relativePathOf(requireNotNull(vaultFilesByEvidenceId[item.id])),
                priority = index + 1,
                createdAtMillis = now,
            )
        }
        outboxDao.insertAll(outboxRows)
        Log.d(LOG_TAG, "seal result=outbox_committed revisionId=$revisionId rows=${outboxRows.size}")

        finishSealAfterOutboxCommitted(assessmentId)
        return SealOutcome.Sealed
    }

    /** The crash-safe tail shared by a fresh [seal] call and launch-time recovery once the
     * outbox is known to be committed: mark every item SEALED, delete plaintext raw/temp
     * files (only the encrypted vault copy survives), flip to READY_TO_SYNC. Idempotent --
     * deleting an already-deleted file is a silent no-op, updating an already-SEALED row is
     * harmless. */
    private suspend fun finishSealAfterOutboxCommitted(assessmentId: String) {
        val items = evidenceDraftDao.getAllForAssessmentOnce(assessmentId).filter { it.state == EvidenceDraftState.READY }
        for (item in items) {
            if (item.finalState != FinalEvidenceState.SEALED) {
                evidenceDraftDao.update(item.copy(finalState = FinalEvidenceState.SEALED))
            }
            val rawFile = fileManager.resolveRelativePath(item.relativePath)
            val finalFile = item.finalRelativePath?.let { fileManager.resolveRelativePath(it) }
            if (finalFile != null && finalFile.absolutePath != rawFile.absolutePath) finalFile.delete()
            rawFile.delete()
        }
        fileManager.deleteP5TempTree(assessmentId)
        assessmentDraftDao.getById(assessmentId)?.let {
            if (it.sealState != SealState.READY_TO_SYNC) {
                assessmentDraftDao.update(it.copy(sealState = SealState.READY_TO_SYNC, sealedAtMillis = it.sealedAtMillis ?: System.currentTimeMillis()))
            }
        }
        Log.d(LOG_TAG, "seal result=ready_to_sync")
    }

    /** Explicit safe discard: removes the current (possibly complete) local seal entirely --
     * vault files, outbox rows -- and returns to DRAFT_EDITABLE with every item's optimisation
     * outcome reset, so the next seal attempt recomputes cleanly. Never silently overwrites a
     * sealed package; this is the only path back to editing (spec part E.4). */
    suspend fun discardAndReopen(assessmentId: String) {
        val assessment = assessmentDraftDao.getById(assessmentId) ?: return
        // P6: once the server has verified+accepted the full sealed package and the worker
        // has submitted it (AssessmentDraftEntity.syncedAtMillis set -- see SyncRepository),
        // the assessor-facing record already exists server-side. A local discard/reopen past
        // that point would silently diverge from what the assessor is reviewing, with no
        // server-side "unsubmit" to keep it honest -- so this is a hard, documented stop, not
        // a state this function tries to handle.
        if (assessment.syncedAtMillis != null) {
            Log.w(LOG_TAG, "discard_and_reopen result=blocked reason=already_synced_and_submitted")
            return
        }
        val items = evidenceDraftDao.getAllForAssessmentOnce(assessmentId).filter { it.state == EvidenceDraftState.READY }

        // A READY_TO_SYNC package already had its raw plaintext deleted (spec G.5) -- the
        // encrypted vault copy is now the only surviving representation. Restore it to the
        // original relativePath location BEFORE wiping the vault, using the OLD revisionId
        // it was actually encrypted under, or discard/reopen would silently destroy evidence
        // instead of safely returning to an editable draft. This decrypt loop is pure
        // filesystem work with no DB write of its own -- see finishDiscardAfterRestore for why
        // that matters for crash-safety.
        val oldRevisionId = assessment.revisionId
        if (assessment.sealState == SealState.READY_TO_SYNC && oldRevisionId != null) {
            restoreItemsFromVault(assessmentId, oldRevisionId, items)
        }
        finishDiscardAfterRestore(assessmentId, assessment, items)
    }

    private fun restoreItemsFromVault(assessmentId: String, revisionId: String, items: List<EvidenceDraftEntity>) {
        val cipher = vaultKeysetProvider.getOrCreateCipher()
        for (item in items) {
            val vaultFile = item.vaultRelativePath?.let { fileManager.resolveRelativePath(it) } ?: continue
            if (!vaultFile.exists()) continue
            cipher.decryptFile(
                vaultFile,
                fileManager.resolveRelativePath(item.relativePath),
                VaultStreamCipher.associatedData(assessmentId, revisionId, item.id, "evidence"),
            )
        }
        Log.d(LOG_TAG, "discard_and_reopen result=restored_from_vault items=${items.size}")
    }

    /** The DB-write half of discard/reopen, split out so reconcileOnLaunch can resume it on
     * its own: the decrypt-to-plaintext loop above writes real evidence files but makes no DB
     * write, so a process death right after it leaves a plaintext copy on disk, the vault
     * still intact, and the assessment row still claiming READY_TO_SYNC -- genuinely dangerous
     * since a stray plaintext copy of evidence the app's own invariant (G.5) promises is
     * encrypted-only now sits unencrypted in app storage with nothing to detect or clean it
     * up. reconcileOnLaunch detects that exact signature (plaintext present at an item's
     * relativePath while its vault file still also exists) and calls this to finish the
     * state transition the user already asked for, rather than leaving the duplicate behind. */
    private suspend fun finishDiscardAfterRestore(
        assessmentId: String,
        assessment: AssessmentDraftEntity,
        items: List<EvidenceDraftEntity>,
    ) {
        // The single assessment-level row flips to DRAFT_EDITABLE FIRST, before anything else
        // here -- it is the one row reconcileOnLaunch's `when` switches on and the UI's
        // `sealed` boolean reads. If the process dies anywhere after this write, the next
        // launch correctly sees an editable draft (never a phantom READY_TO_SYNC) even though
        // per-item resets and vault/outbox cleanup below may not have run yet; reconcileOnLaunch
        // treats any non-sealed assessment as owning no vault/outbox and sweeps them
        // unconditionally, so those leftovers are harmless and self-healing.
        assessmentDraftDao.update(
            assessment.copy(
                sealState = SealState.DRAFT_EDITABLE,
                revisionId = UUID.randomUUID().toString(),
                attestationConfirmed = false,
                attestationAtMillis = null,
                sealedAtMillis = null,
                manifestVaultRelativePath = null,
                signerKeyId = null,
                signerPublicKeyBase64 = null,
                idempotencyKey = null,
            ),
        )
        for (item in items) {
            // A vault/seal ever existed only for items that reached SEALED: the vault stores
            // the FINAL (already-optimised) bytes, never the original raw capture (deleted at
            // seal time, spec G.5), so the plaintext just restored to item.relativePath IS the
            // final bytes, not the raw ones byteSize/widthPx/heightPx still describe. Promote
            // the final metadata onto the base fields before clearing it, or the DB permanently
            // disagrees with the file actually on disk -- wrong budget totals, wrong dimensions
            // for anything that re-reads this item without re-capturing it.
            val wasSealed = item.finalState == FinalEvidenceState.SEALED && item.finalBytes != null
            evidenceDraftDao.update(
                item.copy(
                    byteSize = if (wasSealed) requireNotNull(item.finalBytes) else item.byteSize,
                    widthPx = if (wasSealed) item.finalWidthPx ?: item.widthPx else item.widthPx,
                    heightPx = if (wasSealed) item.finalHeightPx ?: item.heightPx else item.heightPx,
                    durationMillis = if (wasSealed) item.finalDurationMillis ?: item.durationMillis else item.durationMillis,
                    finalState = FinalEvidenceState.NOT_PROCESSED,
                    finalRelativePath = null,
                    finalBytes = null,
                    finalSha256 = null,
                    finalMimeType = null,
                    finalWidthPx = null,
                    finalHeightPx = null,
                    finalDurationMillis = null,
                    vaultRelativePath = null,
                ),
            )
        }

        outboxDao.deleteAllForAssessment(assessmentId)
        fileManager.deleteVaultTree(assessmentId)
        fileManager.deleteP5TempTree(assessmentId)
        Log.d(LOG_TAG, "discard_and_reopen result=completed")
    }

    /** P7: seals a TARGETED reassessment revision -- only the reopened tasks' genuinely new
     * evidence gets encrypted/uploaded; every other task's already-verified evidence is
     * re-declared in the manifest BY REFERENCE (same evidenceId/sha256/bytes/task the server
     * already has), never re-encrypted or re-sent. This is what makes versioned resubmission
     * work even though P6 already deleted those items' local vault files right after their
     * original receipt (see EvidenceDraftEntity.fromPreviousRevision's doc comment) -- the
     * EvidenceDraftEntity row's cached final metadata (finalBytes/finalSha256/...) is the only
     * thing needed to re-declare them honestly, and it survives that deletion.
     *
     * A deliberately separate method from [seal] (not a shared refactor) -- [seal]'s exact
     * behaviour is covered by existing P5 instrumented tests this phase must not disturb;
     * the two share the same signing/vault/outbox primitives, just applied to a different
     * (inherited + new) item set. */
    suspend fun sealTargetedRevision(assessmentId: String, reopenedTaskCodes: Set<String>): SealOutcome {
        val assessment = assessmentDraftDao.getById(assessmentId) ?: return SealOutcome.NoActiveAssessment
        if (assessment.sealState != SealState.FINAL_REVIEW_READY) return SealOutcome.NotReady
        if (!assessment.attestationConfirmed) return SealOutcome.AttestationRequired

        val newItems = evidenceDraftDao.getAllForAssessmentOnce(assessmentId)
            .filter {
                it.state == EvidenceDraftState.READY && it.taskId in reopenedTaskCodes &&
                    it.finalState != FinalEvidenceState.SEALED
            }
        if (newItems.isEmpty()) return SealOutcome.NoEvidence
        if (newItems.any { it.finalState == FinalEvidenceState.NOT_PROCESSED || it.finalState == FinalEvidenceState.QUALITY_FLOOR_EXCEEDED }) {
            return SealOutcome.ItemsNotReady
        }
        val inheritedItems = evidenceDraftDao.getAllForAssessmentOnce(assessmentId)
            .filter {
                it.state == EvidenceDraftState.READY && it.taskId !in reopenedTaskCodes &&
                    it.finalState == FinalEvidenceState.SEALED && !it.fromPreviousRevision
            }

        val revisionId = UUID.randomUUID().toString()
        assessmentDraftDao.update(assessment.copy(sealState = SealState.SEAL_IN_PROGRESS, revisionId = revisionId))
        Log.d(LOG_TAG, "seal_targeted_revision result=started revisionId=$revisionId newItems=${newItems.size} inherited=${inheritedItems.size}")

        val signingKey = ManifestSigner.getOrCreateSigningKey(signingKeyAlias)
        val publicKeyBase64 = Base64.encodeToString(signingKey.certificate.publicKey.encoded, Base64.NO_WRAP)
        val idempotencyKey = "$assessmentId:$revisionId"
        val now = System.currentTimeMillis()

        val sha256ByEvidenceId = mutableMapOf<String, String>()
        val newManifestItems = newItems.map { item ->
            val finalFile = fileManager.resolveRelativePath(requireNotNull(item.finalRelativePath))
            val sha256 = StreamingHasher.sha256Hex(finalFile)
            sha256ByEvidenceId[item.id] = sha256
            ManifestEvidenceItem(
                evidenceId = item.id,
                taskId = item.taskId,
                kind = item.kind.name,
                fileName = finalFile.name,
                bytes = requireNotNull(item.finalBytes),
                sha256 = sha256,
                mimeType = item.finalMimeType ?: "application/octet-stream",
                durationMillis = item.finalDurationMillis,
                widthPx = item.finalWidthPx,
                heightPx = item.finalHeightPx,
                processing = item.finalState.name,
                capturedAtMillis = item.createdAtMillis,
            )
        }
        val inheritedManifestItems = inheritedItems.map { item ->
            ManifestEvidenceItem(
                evidenceId = item.id,
                taskId = item.taskId,
                kind = item.kind.name,
                fileName = File(item.finalRelativePath ?: item.relativePath).name,
                bytes = requireNotNull(item.finalBytes) { "inherited item ${item.id} has no final size" },
                sha256 = requireNotNull(item.finalSha256) { "inherited item ${item.id} has no final hash" },
                mimeType = item.finalMimeType ?: "application/octet-stream",
                durationMillis = item.finalDurationMillis,
                widthPx = item.finalWidthPx,
                heightPx = item.finalHeightPx,
                processing = "INHERITED",
                capturedAtMillis = item.createdAtMillis,
            )
        }
        val allManifestItems = newManifestItems + inheritedManifestItems
        val taskTotals = rules.tasksFile.tasks.map { task ->
            ManifestTaskTotal(task.id, allManifestItems.filter { it.taskId == task.id }.sumOf { it.bytes }, task.budgetBytes)
        }
        val manifest = SealManifest(
            schemaVersion = 1,
            assessmentId = assessmentId,
            revisionId = revisionId,
            qpCode = assessment.qpCode,
            qpVersion = assessment.qpVersion,
            appVersion = appVersion,
            createdAtMillis = assessment.createdAtMillis,
            sealedAtMillis = now,
            attestationConfirmed = true,
            attestationAtMillis = assessment.attestationAtMillis ?: now,
            evidence = allManifestItems,
            taskTotals = taskTotals,
            assessmentFinalBytes = allManifestItems.sumOf { it.bytes },
            assessmentBudgetBytes = rules.tasksFile.finalEvidenceBudgetBytes,
            idempotencyKey = idempotencyKey,
            signerKeyId = signingKeyAlias,
            signerPublicKeyBase64 = publicKeyBase64,
            declarationSummary = buildDeclarationSummary(assessment),
        )
        val canonicalBytes = manifest.canonicalJsonBytes()
        val signature = ManifestSigner.sign(canonicalBytes, signingKey.privateKey)
        if (!ManifestSigner.verify(canonicalBytes, signature, signingKey.certificate.publicKey)) {
            Log.e(LOG_TAG, "seal_targeted_revision result=failed category=self_verification_failed")
            assessmentDraftDao.getById(assessmentId)?.let { assessmentDraftDao.update(it.copy(sealState = SealState.FINAL_REVIEW_READY)) }
            return SealOutcome.VerificationFailed
        }

        val signedPackage = SignedManifestPackage(
            manifestBase64 = Base64.encodeToString(canonicalBytes, Base64.NO_WRAP),
            signatureBase64 = Base64.encodeToString(signature, Base64.NO_WRAP),
            algorithm = ManifestSigner.SIGNATURE_ALGORITHM,
            signerKeyId = signingKeyAlias,
            signerPublicKeyBase64 = publicKeyBase64,
        )
        val manifestPlainFile = File(fileManager.sealTempDir(assessmentId), "manifest_package.json")
        manifestPlainFile.writeBytes(signedPackage.toJsonBytes())

        val vaultDir = fileManager.vaultDir(assessmentId, revisionId)
        val cipher = vaultKeysetProvider.getOrCreateCipher()

        val manifestVaultFile = File(vaultDir, "manifest.vault")
        cipher.encryptFile(
            manifestPlainFile,
            manifestVaultFile,
            VaultStreamCipher.associatedData(assessmentId, revisionId, "manifest", "manifest"),
        )

        // Only the GENUINELY NEW items are encrypted into this revision's vault -- inherited
        // items were already uploaded/verified under an earlier revision, and P6 already
        // deleted their local vault file right after that receipt; there is nothing left to
        // re-encrypt, and nothing new needs sending for them.
        val vaultFilesByEvidenceId = mutableMapOf<String, File>()
        for (item in newItems) {
            val finalFile = fileManager.resolveRelativePath(requireNotNull(item.finalRelativePath))
            val vaultFile = File(vaultDir, "${item.id}.vault")
            cipher.encryptFile(
                finalFile,
                vaultFile,
                VaultStreamCipher.associatedData(assessmentId, revisionId, item.id, "evidence"),
            )
            vaultFilesByEvidenceId[item.id] = vaultFile
            evidenceDraftDao.update(
                item.copy(
                    vaultRelativePath = fileManager.relativePathOf(vaultFile),
                    finalSha256 = sha256ByEvidenceId[item.id],
                ),
            )
        }

        assessmentDraftDao.getById(assessmentId)?.let {
            assessmentDraftDao.update(
                it.copy(
                    sealState = SealState.VAULT_READY,
                    manifestVaultRelativePath = fileManager.relativePathOf(manifestVaultFile),
                    signerKeyId = signingKeyAlias,
                    signerPublicKeyBase64 = publicKeyBase64,
                    idempotencyKey = idempotencyKey,
                ),
            )
        }
        Log.d(LOG_TAG, "seal_targeted_revision result=vault_ready revisionId=$revisionId")

        val outboxRows = mutableListOf(
            OutboxItemEntity(
                id = UUID.randomUUID().toString(),
                assessmentId = assessmentId,
                revisionId = revisionId,
                idempotencyKey = idempotencyKey,
                kind = OutboxItemKind.MANIFEST,
                evidenceId = null,
                taskId = null,
                vaultRelativePath = fileManager.relativePathOf(manifestVaultFile),
                priority = 0,
                createdAtMillis = now,
            ),
        )
        newItems.forEachIndexed { index, item ->
            outboxRows += OutboxItemEntity(
                id = UUID.randomUUID().toString(),
                assessmentId = assessmentId,
                revisionId = revisionId,
                idempotencyKey = idempotencyKey,
                kind = OutboxItemKind.EVIDENCE,
                evidenceId = item.id,
                taskId = item.taskId,
                vaultRelativePath = fileManager.relativePathOf(requireNotNull(vaultFilesByEvidenceId[item.id])),
                priority = index + 1,
                createdAtMillis = now,
            )
        }
        outboxDao.insertAll(outboxRows)
        Log.d(LOG_TAG, "seal_targeted_revision result=outbox_committed revisionId=$revisionId rows=${outboxRows.size}")

        for (item in newItems) {
            // Preserve the hash and vault path written during encryption; the
            // pre-encryption item snapshot still has their old values.
            evidenceDraftDao.update(item.copy(
                finalState = FinalEvidenceState.SEALED,
                finalSha256 = sha256ByEvidenceId.getValue(item.id),
                vaultRelativePath = fileManager.relativePathOf(vaultFilesByEvidenceId.getValue(item.id)),
            ))
            val rawFile = fileManager.resolveRelativePath(item.relativePath)
            val finalFile = item.finalRelativePath?.let { fileManager.resolveRelativePath(it) }
            if (finalFile != null && finalFile.absolutePath != rawFile.absolutePath) finalFile.delete()
            rawFile.delete()
        }
        // The OLD (now-superseded) item(s) for a reopened task become historical -- kept in
        // Room (immutable, still viewable -- see docs/gates/P7.md section 3), excluded from
        // the active working set.
        val newItemIds = newItems.map { it.id }.toSet()
        val supersededItems = evidenceDraftDao.getAllForAssessmentOnce(assessmentId).filter {
            it.taskId in reopenedTaskCodes && it.state == EvidenceDraftState.READY &&
                it.finalState == FinalEvidenceState.SEALED && it.id !in newItemIds
        }
        for (item in supersededItems) {
            evidenceDraftDao.update(item.copy(fromPreviousRevision = true))
        }
        fileManager.deleteP5TempTree(assessmentId)

        assessmentDraftDao.getById(assessmentId)?.let {
            assessmentDraftDao.update(
                it.copy(
                    sealState = SealState.READY_TO_SYNC,
                    sealedAtMillis = now,
                    // A fresh revision must actually attempt to sync -- syncedAtMillis
                    // otherwise still holds the PREVIOUS (already-submitted) revision's
                    // value, and SyncRepository.syncAssessment's very first check would
                    // short-circuit to Success without ever looking at the new outbox rows.
                    syncedAtMillis = null,
                ),
            )
        }
        Log.d(LOG_TAG, "seal_targeted_revision result=ready_to_sync")
        return SealOutcome.Sealed
    }

    private fun buildDeclarationSummary(assessment: AssessmentDraftEntity): ManifestDeclarationSummary? {
        val matchOutput = assessment.matchOutputJson?.let {
            try {
                DRAFT_JSON.decodeFromString<MatchOutput>(it)
            } catch (e: Exception) {
                Log.w(LOG_TAG, "build_declaration_summary result=undecodable_match_output")
                null
            }
        } ?: return null
        val gapTaskCodes = matchOutput.applicableTasks.filter { it.extraEvidenceNeeded }.mapNotNull { it.task }
        return ManifestDeclarationSummary(
            matchResult = matchOutput.matchResult,
            overallCoverage = matchOutput.overallCoverage,
            gapTaskCodes = gapTaskCodes,
            matchReasons = matchOutput.because,
        )
    }
}
