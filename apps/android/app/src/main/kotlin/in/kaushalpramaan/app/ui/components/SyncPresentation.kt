package `in`.kaushalpramaan.app.ui.components

import androidx.work.WorkInfo
import `in`.kaushalpramaan.app.data.draft.EvidenceDraftEntity
import `in`.kaushalpramaan.app.data.draft.OutboxItemEntity
import `in`.kaushalpramaan.app.data.draft.OutboxItemKind
import `in`.kaushalpramaan.app.data.draft.SyncState

enum class SyncPhase { BEFORE_SEAL, OFFLINE, QUEUED, UPLOADING, VERIFYING, RETRYING, FAILED, STALLED, SUBMITTED }
data class SyncPresentation(
    val phase: SyncPhase,
    val uploadedBytes: Long = 0,
    val totalBytes: Long = 0,
    val completedItems: Int = 0,
    val totalItems: Int = 0,
) {
    val fraction: Float get() = if (phase == SyncPhase.SUBMITTED) 1f else if (totalBytes > 0) (uploadedBytes.toFloat() / totalBytes).coerceIn(0f, 1f) else 0f
    val problem: Boolean get() = phase in setOf(SyncPhase.OFFLINE, SyncPhase.RETRYING, SyncPhase.FAILED, SyncPhase.STALLED)
    val active: Boolean get() = phase == SyncPhase.QUEUED || phase == SyncPhase.UPLOADING || phase == SyncPhase.VERIFYING
}

/** Acknowledged bytes and actual scheduler state only; no simulated progress. */
fun syncPresentation(sealed: Boolean, submitted: Boolean, online: Boolean,
    rows: List<OutboxItemEntity>, evidence: List<EvidenceDraftEntity>,
    workState: WorkInfo.State?, attempts: Int = 0, lastActivityAt: Long = 0,
    now: Long = System.currentTimeMillis(),
): SyncPresentation {
    val sizes = evidence.associate { it.id to (it.finalBytes ?: it.byteSize) }
    val mediaRows = rows.filter { it.kind == OutboxItemKind.EVIDENCE }
    val total = mediaRows.sumOf { sizes[it.evidenceId] ?: 0L }
    val sent = mediaRows.sumOf { row ->
        val size = sizes[row.evidenceId] ?: 0L
        if (row.syncState == SyncState.SYNCED) size else row.bytesUploaded.coerceIn(0L, size)
    }
    val phase = when {
        !sealed -> SyncPhase.BEFORE_SEAL
        submitted -> SyncPhase.SUBMITTED
        !online -> SyncPhase.OFFLINE
        workState == WorkInfo.State.ENQUEUED && attempts == 0 -> SyncPhase.QUEUED
        workState == WorkInfo.State.FAILED || workState == WorkInfo.State.CANCELLED -> SyncPhase.FAILED
        workState == WorkInfo.State.RUNNING && lastActivityAt > 0 && now - lastActivityAt >= 60_000 -> SyncPhase.STALLED
        workState == WorkInfo.State.RUNNING && (rows.isNotEmpty() && rows.all { it.syncState == SyncState.SYNCED } || rows.any { it.syncState == SyncState.VERIFYING } || total > 0 && sent >= total) -> SyncPhase.VERIFYING
        workState == WorkInfo.State.RUNNING -> SyncPhase.UPLOADING
        rows.any { it.syncState == SyncState.FAILED_ACTION_REQUIRED } -> SyncPhase.FAILED
        attempts > 0 || rows.any { it.syncState == SyncState.RETRYING } -> SyncPhase.RETRYING
        else -> SyncPhase.QUEUED
    }
    return SyncPresentation(phase, sent, total, rows.count { it.syncState == SyncState.SYNCED }, rows.size)
}
