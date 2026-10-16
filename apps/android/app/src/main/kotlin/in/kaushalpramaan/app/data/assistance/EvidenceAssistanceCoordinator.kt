package `in`.kaushalpramaan.app.data.assistance

import android.content.Context
import androidx.room.withTransaction
import androidx.work.*
import `in`.kaushalpramaan.app.data.draft.*
import `in`.kaushalpramaan.core.seal.*
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.withContext
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** Room owns identity/state; WorkManager owns execution. AssistanceRunner's shared
 * semaphore bounds native decoders and MediaPipe engines to one active job. */
class EvidenceAssistanceCoordinator(
    private val context: Context,
    private val db: AppDatabase,
    private val files: EvidenceFileManager,
) {
    suspend fun schedule(evidenceId: String, retry: Boolean = false, recover: Boolean = false) {
        try { scheduling.withLock { scheduleInternal(evidenceId, retry, recover) } }
        catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) {
            // Assistance scheduling is advisory. Capture/P5 success remains success;
            // a durable queued row is recoverable after an enqueue interruption.
        }
    }

    private suspend fun scheduleInternal(evidenceId: String, retry: Boolean, recover: Boolean) = withContext(Dispatchers.IO) {
        val item = db.evidenceDraftDao().getById(evidenceId) ?: return@withContext
        val assessment = db.assessmentDraftDao().getById(item.assessmentId) ?: return@withContext
        if (!editable(item, assessment)) return@withContext
        val path = inputPath(item)
        val file = files.resolveRelativePath(path)
        if (!file.isFile) return@withContext
        val hash = StreamingHasher.sha256Hex(file)
        val duration = duration(item)
        val next = db.withTransaction {
            val current = db.evidenceDraftDao().getById(evidenceId) ?: return@withTransaction null
            val parent = db.assessmentDraftDao().getById(item.assessmentId) ?: return@withTransaction null
            if (!editable(current, parent) || inputPath(current) != path || duration(current) != duration) return@withTransaction null
            val old = db.assistanceDao().get(evidenceId)
            val same = old?.inputSha256 == hash && old.revisionNumber == parent.currentRevisionNumber && old.durationMs == duration
            if (same && old!!.inputPath != path) {
                // Byte equality is proven by SHA-256, and duration is unchanged.
                // A running worker can finish reading its equivalent original file;
                // its generation/hash guards still bind the result to these bytes.
                db.assistanceDao().put(old.copy(inputPath = path))
                if (!retry && !recover) return@withTransaction null
            }
            if (same && recover && !retry) {
                val active = WorkManager.getInstance(context).getWorkInfosForUniqueWork(tag(evidenceId)).get()
                    .any { !it.state.isFinished && it.tags.contains(old!!.generation) }
                if (active) return@withTransaction null
            }
            if (same && !retry && !(recover && old!!.status in setOf("QUEUED", "RUNNING"))) return@withTransaction null
            val missingVideoDuration = current.kind == `in`.kaushalpramaan.app.data.EvidenceType.VIDEO && duration == null
            AssistanceRecord(evidenceId, item.assessmentId, item.taskId, parent.currentRevisionNumber,
                UUID.randomUUID().toString(), path, hash, duration,
                if (missingVideoDuration) "UNAVAILABLE" else "QUEUED",
                if (missingVideoDuration) "unavailable" else "queued", null, null,
                if (missingVideoDuration) "MEDIA_UNAVAILABLE" else null)
                .also { db.assistanceDao().put(it) }
        } ?: return@withContext
        if (next.status != "QUEUED") return@withContext
        WorkManager.getInstance(context).cancelAllWorkByTag(tag(evidenceId))
        enqueue(next)
    }

    private fun enqueue(record: AssistanceRecord) {
        val request = OneTimeWorkRequestBuilder<EvidenceAssistanceWorker>()
            .setInputData(workDataOf("evidenceId" to record.evidenceId, "generation" to record.generation))
            .addTag(tag(record.evidenceId)).addTag(record.generation).build()
        WorkManager.getInstance(context).enqueueUniqueWork(tag(record.evidenceId), ExistingWorkPolicy.REPLACE, request)
    }

    suspend fun cancel(evidenceId: String) {
        scheduling.withLock {
            db.withTransaction {
                val old = db.assistanceDao().get(evidenceId) ?: return@withTransaction
                val item = db.evidenceDraftDao().getById(evidenceId) ?: return@withTransaction
                val parent = db.assessmentDraftDao().getById(item.assessmentId) ?: return@withTransaction
                if (editable(item, parent)) db.assistanceDao().put(old.copy(generation = UUID.randomUUID().toString(),
                    status = "NOT_RUN", stage = "cancelled", resultJson = null, errorCategory = "CANCELLED"))
            }
            WorkManager.getInstance(context).cancelAllWorkByTag(tag(evidenceId))
        }
    }

    suspend fun recover(assessmentId: String) {
        db.evidenceDraftDao().getAllForAssessmentOnce(assessmentId).forEach { schedule(it.id, recover = true) }
    }

    /** Called after SEAL_IN_PROGRESS freezes writes. All reads/writes below form one Room
     * transaction. No inference is awaited; unfinished work is an honest signed status.
     * Inherited evidence keeps its exact original snapshot, including its original revision. */
    suspend fun snapshot(item: EvidenceDraftEntity, hash: String, revisionId: String, revisionNumber: Int): AssistanceSnapshot = db.withTransaction {
        val record = db.assistanceDao().get(item.id)
        val matching = record?.inputSha256 == hash && record.revisionNumber == revisionNumber && record.durationMs == duration(item)
        val result = if (matching) record?.resultJson?.let { JSON.decodeFromString<AssistanceSnapshot>(it) } else null
        val snapshot = (result ?: AssistanceSnapshot(assessmentId = item.assessmentId, taskId = item.taskId,
            evidenceId = item.id, revisionId = revisionId, revisionNumber = revisionNumber, mediaSha256 = hash,
            durationMs = duration(item), status = if (matching) AssistanceStatus.valueOf(record!!.status) else AssistanceStatus.NOT_RUN,
            errorCategory = if (matching) record?.errorCategory?.let { AssistanceError.valueOf(it) } else null))
            .copy(revisionId = revisionId)
        snapshot.validateBinding(item.assessmentId, item.taskId, item.id, hash, duration(item))
        val json = JSON.encodeToString(AssistanceSnapshot.serializer(), snapshot)
        val frozen = record ?: AssistanceRecord(item.id, item.assessmentId, item.taskId, revisionNumber,
            UUID.randomUUID().toString(), inputPath(item), hash, duration(item), snapshot.status.name, "snapshot", null, null, null)
        db.assistanceDao().put(frozen.copy(sealedSnapshotJson = json))
        snapshot
    }

    suspend fun inherited(item: EvidenceDraftEntity): AssistanceSnapshot? = db.assistanceDao().get(item.id)?.sealedSnapshotJson
        ?.let { JSON.decodeFromString<AssistanceSnapshot>(it) }

    suspend fun storeBoundedSnapshot(snapshot: AssistanceSnapshot) = db.withTransaction {
        db.assistanceDao().get(snapshot.evidenceId)?.let {
            db.assistanceDao().put(it.copy(sealedSnapshotJson = JSON.encodeToString(AssistanceSnapshot.serializer(), snapshot)))
        }
    }

    companion object {
        // Preserve Room-generation and WorkManager-operation order across callers and
        // coordinator instances. An older retry must not replace a newer generation's job.
        private val scheduling = Mutex()
        val JSON = SealManifest.CANONICAL_JSON
        fun tag(id: String) = "kp_assistance_$id"
        fun inputPath(item: EvidenceDraftEntity) = if (item.finalState in setOf(FinalEvidenceState.FITS_AS_IS, FinalEvidenceState.OPTIMIZED))
            item.finalRelativePath ?: item.relativePath else item.relativePath
        fun duration(item: EvidenceDraftEntity) = if (item.kind == `in`.kaushalpramaan.app.data.EvidenceType.VIDEO)
            item.finalDurationMillis ?: item.durationMillis else null
        fun editable(item: EvidenceDraftEntity, assessment: AssessmentDraftEntity) = item.state == EvidenceDraftState.READY &&
            item.finalState != FinalEvidenceState.SEALED && !item.fromPreviousRevision && assessment.state == AssessmentDraftState.ACTIVE &&
            assessment.sealState in setOf(SealState.DRAFT_EDITABLE, SealState.PROCESSING, SealState.FINAL_REVIEW_READY)
    }
}
