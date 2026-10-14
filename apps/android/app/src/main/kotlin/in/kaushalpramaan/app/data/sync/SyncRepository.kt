package `in`.kaushalpramaan.app.data.sync

import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.data.draft.AssessmentDraftDao
import `in`.kaushalpramaan.app.data.draft.AssessmentDraftEntity
import `in`.kaushalpramaan.app.data.draft.EvidenceDraftDao
import `in`.kaushalpramaan.app.data.draft.EvidenceFileManager
import `in`.kaushalpramaan.app.data.draft.OutboxDao
import `in`.kaushalpramaan.app.data.draft.OutboxItemEntity
import `in`.kaushalpramaan.app.data.draft.OutboxItemKind
import `in`.kaushalpramaan.app.data.draft.SealState
import `in`.kaushalpramaan.app.data.draft.SyncState
import `in`.kaushalpramaan.core.seal.VaultCipher
import `in`.kaushalpramaan.core.seal.VaultKeysetProvider
import `in`.kaushalpramaan.core.seal.VaultStreamCipher
import android.util.Log
import java.security.MessageDigest

/** Outcome of one [SyncRepository.syncAssessment] call -- the sole thing [SyncWorker] maps to
 * a WorkManager [androidx.work.ListenableWorker.Result]. */
sealed class SyncRunOutcome {
    /** Nothing to do (not sealed, already synced, or discarded out from under this run), or
     * every declared item is now server-verified and the assessment has been submitted. */
    object Success : SyncRunOutcome()
    /** A transient failure (network, timeout, 5xx) -- WorkManager should back off and retry
     * the whole job; already-synced items are skipped instantly on the next attempt. */
    data class Retryable(val category: SyncErrorCategory) : SyncRunOutcome()
    /** A non-retryable rejection (wrong hash, bad signature, superseded revision) -- retrying
     * the same bytes will never succeed; the worker needs a new seal (P5's existing discard/
     * reopen), not another WorkManager attempt. */
    data class Terminal(val category: SyncErrorCategory) : SyncRunOutcome()
}

private const val LOG_TAG = "KP-Sync"
private const val CHUNK_SIZE_BYTES = 1 * 1024 * 1024 // 1 MiB, per P6 spec -- never configurable

/**
 * P6's sync orchestrator -- the single place that consumes P5's READY_TO_SYNC outbox, the
 * only writer of every [OutboxItemEntity] sync-progress column, and the only code that ever
 * deletes a vault file or outbox row. Designed to be safely re-entered from scratch at any
 * point (force-stop, duplicate WorkManager invocation, a second manual "sync now") -- every
 * step either reads real persisted state before acting, or is itself idempotent against the
 * server.
 */
class SyncRepository(
    private val assessmentDraftDao: AssessmentDraftDao,
    private val evidenceDraftDao: EvidenceDraftDao,
    private val outboxDao: OutboxDao,
    private val fileManager: EvidenceFileManager,
    private val vaultKeysetProvider: VaultKeysetProvider,
    private val endpointConfig: SyncEndpointConfig,
) {
    suspend fun syncAssessment(assessmentId: String): SyncRunOutcome {
        val assessment = assessmentDraftDao.getById(assessmentId) ?: return SyncRunOutcome.Success
        if (assessment.syncedAtMillis != null) return SyncRunOutcome.Success
        if (assessment.sealState != SealState.READY_TO_SYNC) return SyncRunOutcome.Success
        val revisionId = assessment.revisionId ?: return SyncRunOutcome.Success

        val bootstrapped = try {
            ensureBootstrapped(assessment)
        } catch (e: SyncApiException) {
            Log.w(LOG_TAG, "sync result=bootstrap_failed category=${e.category}")
            return e.toOutcome()
        }

        val apiClient = SyncApiClient(endpointConfig, bootstrapped.serverWorkerToken!!)
        val serverAssessmentId = bootstrapped.serverAssessmentId!!

        val rows = outboxDao.getAllForAssessmentOnce(assessmentId).filter { it.revisionId == revisionId }
        for (row in rows.sortedBy { it.priority }) {
            if (row.syncState == SyncState.SYNCED) continue
            val outcome = syncOneItem(serverAssessmentId, revisionId, row, apiClient)
            if (outcome != null) {
                Log.w(LOG_TAG, "sync result=item_failed kind=${row.kind} category=${outcome.categoryName()}")
                return outcome
            }
        }

        return finishIfAllSynced(assessmentId, serverAssessmentId, revisionId, apiClient)
    }

    private fun SyncRunOutcome.categoryName(): String = when (this) {
        is SyncRunOutcome.Retryable -> category.name
        is SyncRunOutcome.Terminal -> category.name
        SyncRunOutcome.Success -> "none"
    }

    private fun SyncApiException.toOutcome(): SyncRunOutcome =
        if (category.retryable) SyncRunOutcome.Retryable(category) else SyncRunOutcome.Terminal(category)

    /** Establishes server identity + the server-side assessment exactly once (idempotent:
     * calling it again when already bootstrapped is a cheap no-op that just re-reads the
     * cached row). See docs/gates/P6.md's "worker identity" design decision. */
    private suspend fun ensureBootstrapped(assessment: AssessmentDraftEntity): AssessmentDraftEntity {
        if (assessment.serverAssessmentId != null && assessment.serverWorkerToken != null) return assessment

        val bootstrap = SyncBootstrapClient(endpointConfig)
        val deviceWorkerId = assessment.workerId ?: "KP-${assessment.id.take(8).uppercase()}"
        val workerId = bootstrap.registerWorker(deviceWorkerId, "Worker")
        val packId = bootstrap.resolvePackId(assessment.qpCode, assessment.qpVersion)
        val (serverAssessmentId, workerToken) = bootstrap.createAssessment(workerId, packId)

        val updated = assessment.copy(serverAssessmentId = serverAssessmentId, serverWorkerToken = workerToken)
        assessmentDraftDao.update(updated)
        Log.d(LOG_TAG, "sync result=bootstrapped serverAssessmentId=$serverAssessmentId")
        return updated
    }

    /** Returns null on success, or the [SyncRunOutcome] to stop the whole run with. */
    private suspend fun syncOneItem(
        serverAssessmentId: Long, revisionId: String, row: OutboxItemEntity, apiClient: SyncApiClient,
    ): SyncRunOutcome? {
        val vaultFile = fileManager.resolveRelativePath(row.vaultRelativePath)
        val cipher = vaultKeysetProvider.getOrCreateCipher()

        return try {
            when (row.kind) {
                OutboxItemKind.MANIFEST -> syncManifestItem(serverAssessmentId, revisionId, row, vaultFile, cipher, apiClient)
                OutboxItemKind.EVIDENCE -> syncEvidenceItem(serverAssessmentId, revisionId, row, vaultFile, cipher, apiClient)
            }
            null
        } catch (e: SyncApiException) {
            Log.w(LOG_TAG, "sync result=item_exception kind=${row.kind} category=${e.category} message=${e.message}")
            markAttemptFailed(row, e.category)
            e.toOutcome()
        }
    }

    private suspend fun markAttemptFailed(row: OutboxItemEntity, category: SyncErrorCategory) {
        outboxDao.update(
            row.copy(
                syncState = if (category.retryable) SyncState.RETRYING else SyncState.FAILED_ACTION_REQUIRED,
                lastErrorCategory = category.name,
                retryCount = row.retryCount + 1,
                lastAttemptAtMillis = System.currentTimeMillis(),
            ),
        )
    }

    // ---- manifest item: small enough to fully decrypt into memory (bounded by the server's
    // own MANIFEST_MAX_BYTES ceiling, a JSON metadata document, never media bytes -- see
    // server/app/manifest_verify.py) ----

    private suspend fun syncManifestItem(
        serverAssessmentId: Long, revisionId: String, row: OutboxItemEntity,
        vaultFile: java.io.File, cipher: VaultCipher, apiClient: SyncApiClient,
    ) {
        outboxDao.update(row.copy(syncState = SyncState.UPLOADING, lastAttemptAtMillis = System.currentTimeMillis()))
        val aad = VaultStreamCipher.associatedData(row.assessmentId, revisionId, "manifest", "manifest")
        val plaintext = cipher.openDecryptingStream(vaultFile, aad).use { it.readBytes() }
        val sha256 = sha256Hex(plaintext)

        val session = recoverOrOpenManifestSession(serverAssessmentId, revisionId, plaintext.size.toLong(), row, apiClient)
        uploadRemainingBytes(session.id, session.receivedBytes, plaintext, row, apiClient)

        val receipt = apiClient.completeManifest(session.id, sha256)
        if (receipt.status == "rejected") {
            throw SyncApiException(SyncErrorCategory.SIGNATURE_REJECTED, message = receipt.rejectionReason)
        }
        markSynced(row, receipt.manifestId)
    }

    private suspend fun recoverOrOpenManifestSession(
        serverAssessmentId: Long, revisionId: String, sizeBytes: Long, row: OutboxItemEntity, apiClient: SyncApiClient,
    ): UploadSessionOut {
        val existingId = row.serverSessionId
        if (existingId != null) {
            val status = try {
                apiClient.getSessionStatus(existingId)
            } catch (e: SyncApiException) {
                null // session gone/expired -- fall through to opening a fresh (recoverable) one
            }
            if (status != null) return status
        }
        val opened = apiClient.openOrRecoverManifestSession(serverAssessmentId, revisionId, sizeBytes)
        outboxDao.update(row.copy(serverSessionId = opened.id, syncState = SyncState.UPLOADING))
        return opened
    }

    // ---- evidence item: bounded 1 MiB streaming decrypt, never the whole file in memory ----

    private suspend fun syncEvidenceItem(
        serverAssessmentId: Long, revisionId: String, row: OutboxItemEntity,
        vaultFile: java.io.File, cipher: VaultCipher, apiClient: SyncApiClient,
    ) {
        val evidenceId = row.evidenceId ?: throw SyncApiException(SyncErrorCategory.UNKNOWN_SERVER_ERROR, message = "evidence row missing evidenceId")
        val taskId = row.taskId ?: throw SyncApiException(SyncErrorCategory.UNKNOWN_SERVER_ERROR, message = "evidence row missing taskId")
        val evidence = evidenceDraftDao.getById(evidenceId)
            ?: throw SyncApiException(SyncErrorCategory.UNKNOWN_SERVER_ERROR, message = "evidence draft not found")
        val sizeBytes = evidence.finalBytes
            ?: throw SyncApiException(SyncErrorCategory.UNKNOWN_SERVER_ERROR, message = "evidence has no final size")
        val mime = evidence.finalMimeType
            ?: throw SyncApiException(SyncErrorCategory.UNKNOWN_SERVER_ERROR, message = "evidence has no final mime type")
        // P5 already computed and stored this (StreamingHasher.sha256Hex, before encryption) --
        // reuse it rather than paying for a second full-file decrypt pass just to re-hash
        // plaintext this app itself produced and never mutates. The server independently
        // recomputes the hash from its own stored bytes regardless (never trusts this value
        // alone), so this is purely an efficiency choice, not a weakened integrity check.
        val sha256 = evidence.finalSha256
            ?: throw SyncApiException(SyncErrorCategory.UNKNOWN_SERVER_ERROR, message = "evidence has no final hash")
        val kindString = if (evidence.kind == EvidenceType.PHOTO) "photo" else "video"

        outboxDao.update(row.copy(syncState = SyncState.UPLOADING, lastAttemptAtMillis = System.currentTimeMillis()))
        val session = recoverOrOpenEvidenceSession(
            serverAssessmentId, taskId, kindString, mime, sizeBytes, revisionId, evidenceId, row, apiClient,
        )

        val aad = VaultStreamCipher.associatedData(row.assessmentId, revisionId, evidenceId, "evidence")
        cipher.openDecryptingStream(vaultFile, aad).use { stream ->
            skipBytes(stream, session.receivedBytes)
            uploadStreamFrom(session.id, session.receivedBytes, sizeBytes, stream, row, apiClient)
        }

        val receipt = apiClient.completeEvidence(session.id, sha256)
        markSynced(row, receipt.evidenceId)
    }

    private suspend fun recoverOrOpenEvidenceSession(
        serverAssessmentId: Long, taskCode: String, kind: String, mime: String, sizeBytes: Long,
        revisionId: String, clientEvidenceId: String, row: OutboxItemEntity, apiClient: SyncApiClient,
    ): UploadSessionOut {
        val existingId = row.serverSessionId
        if (existingId != null) {
            val status = try {
                apiClient.getSessionStatus(existingId)
            } catch (e: SyncApiException) {
                null
            }
            if (status != null) return status
        }
        val opened = apiClient.openOrRecoverEvidenceSession(
            serverAssessmentId, taskCode, kind, mime, sizeBytes, revisionId, clientEvidenceId,
        )
        outboxDao.update(row.copy(serverSessionId = opened.id, syncState = SyncState.UPLOADING))
        return opened
    }

    /** Reads and discards exactly [count] plaintext bytes -- the only way to "seek" a
     * sequential streaming-AEAD decrypt when resuming an upload the server already has a
     * prefix of. */
    private fun skipBytes(stream: java.io.InputStream, count: Long) {
        var remaining = count
        val buffer = ByteArray(minOf(CHUNK_SIZE_BYTES.toLong(), maxOf(remaining, 1L)).toInt())
        while (remaining > 0) {
            val n = stream.read(buffer, 0, minOf(buffer.size.toLong(), remaining).toInt())
            if (n < 0) break
            remaining -= n
        }
    }

    private suspend fun uploadStreamFrom(
        sessionId: Long, startAtByte: Long, totalBytes: Long, stream: java.io.InputStream,
        row: OutboxItemEntity, apiClient: SyncApiClient,
    ) {
        var received = startAtByte
        var chunkIndex = (startAtByte / CHUNK_SIZE_BYTES).toInt()
        val buffer = ByteArray(CHUNK_SIZE_BYTES)
        while (received < totalBytes) {
            val n = readFully(stream, buffer)
            if (n <= 0) break
            val ack = apiClient.putChunk(sessionId, chunkIndex, buffer.copyOf(n))
            received = ack.receivedBytes
            chunkIndex = ack.nextChunkIndex
            outboxDao.update(row.copy(bytesUploaded = received, syncState = SyncState.UPLOADING))
        }
    }

    private suspend fun uploadRemainingBytes(
        sessionId: Long, startAtByte: Long, full: ByteArray, row: OutboxItemEntity, apiClient: SyncApiClient,
    ) {
        var offset = startAtByte.toInt()
        var chunkIndex = (startAtByte / CHUNK_SIZE_BYTES).toInt()
        while (offset < full.size) {
            val end = minOf(offset + CHUNK_SIZE_BYTES, full.size)
            val ack = apiClient.putChunk(sessionId, chunkIndex, full.copyOfRange(offset, end))
            offset = end
            chunkIndex = ack.nextChunkIndex
            outboxDao.update(row.copy(bytesUploaded = offset.toLong(), syncState = SyncState.UPLOADING))
        }
    }

    private fun readFully(stream: java.io.InputStream, buffer: ByteArray): Int {
        var total = 0
        while (total < buffer.size) {
            val n = stream.read(buffer, total, buffer.size - total)
            if (n < 0) break
            total += n
        }
        return total
    }

    private suspend fun markSynced(row: OutboxItemEntity, serverObjectId: Long) {
        val now = System.currentTimeMillis()
        outboxDao.update(
            row.copy(
                syncState = SyncState.SYNCED, serverObjectId = serverObjectId,
                receiptVerifiedAtMillis = now, lastErrorCategory = null,
            ),
        )
        // Safe only now: the server has independently verified this exact item's hash/size/
        // binding (and, for evidence, cross-checked it against the signed manifest).
        fileManager.deleteQuietly(fileManager.resolveRelativePath(row.vaultRelativePath))
        Log.d(LOG_TAG, "sync result=item_synced kind=${row.kind} serverObjectId=$serverObjectId")
    }

    private suspend fun finishIfAllSynced(
        assessmentId: String, serverAssessmentId: Long, revisionId: String, apiClient: SyncApiClient,
    ): SyncRunOutcome {
        val rows = outboxDao.getAllForAssessmentOnce(assessmentId).filter { it.revisionId == revisionId }
        if (rows.any { it.syncState != SyncState.SYNCED }) return SyncRunOutcome.Success // this run made progress; more remains

        try {
            apiClient.submitAssessment(serverAssessmentId)
        } catch (e: SyncApiException) {
            if (e.httpCode == 409) {
                // Already submitted by a previous attempt whose local write was lost --
                // idempotent-equivalent, not a real failure. Any other 409 (e.g. a real
                // server-side state problem) still surfaces as a terminal/retryable outcome.
                Log.d(LOG_TAG, "sync result=submit_already_done")
            } else {
                return e.toOutcome()
            }
        }

        outboxDao.deleteAllForAssessment(assessmentId)
        fileManager.deleteVaultTree(assessmentId)
        val assessment = assessmentDraftDao.getById(assessmentId)
        if (assessment != null) {
            assessmentDraftDao.update(assessment.copy(syncedAtMillis = System.currentTimeMillis()))
        }
        Log.d(LOG_TAG, "sync result=submit assessment=$assessmentId state=SUBMITTED")
        return SyncRunOutcome.Success
    }

    private fun sha256Hex(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
}
