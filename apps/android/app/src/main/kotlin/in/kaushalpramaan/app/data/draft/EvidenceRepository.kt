package `in`.kaushalpramaan.app.data.draft

import `in`.kaushalpramaan.app.BuildConfig
import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.core.mapping.MatchOutput
import `in`.kaushalpramaan.core.mapping.Rules
import android.util.Log
import java.io.File
import java.util.UUID
import kotlinx.coroutines.flow.Flow

/** Structured, content-free diagnostic tag: only safe technical state (task id, lifecycle
 * state, byte counts, error categories) is ever logged here -- never a file path, media
 * content, database passphrase, or personal information. */
private const val LOG_TAG = "KP-Capture"

enum class CaptureRejectionReason { INSUFFICIENT_FREE_SPACE, TASK_BUDGET_EXHAUSTED, TOTAL_BUDGET_EXHAUSTED }

sealed class BeginCaptureResult {
    data class Started(val evidenceId: String, val stagingFile: File, val ceilingBytes: Long) : BeginCaptureResult()
    data class Rejected(val reason: CaptureRejectionReason) : BeginCaptureResult()
}

sealed class FinalizeResult {
    data class Ready(val evidence: EvidenceDraftEntity) : FinalizeResult()
    data object Failed : FinalizeResult()
    /** The real on-disk file (read via [File.length], never a caller-supplied number) was
     * larger than the task's or the assessment's remaining budget, recomputed fresh against
     * the current database state. The capture is rejected and deleted -- never promoted,
     * never retained as READY -- and if this was a replacement, the old READY item it would
     * have replaced is untouched and still valid. */
    data class RejectedOverLimit(val actualBytes: Long, val allowedBytes: Long) : FinalizeResult()
}

/**
 * The single orchestration point for P4 draft persistence: creates/resumes the one
 * active [AssessmentDraftEntity], enforces the T1-T5 + total safety ceilings against
 * the canonical [Rules] (never a second, hand-duplicated copy of tasks.json's
 * budgets), and keeps [EvidenceDraftEntity] rows and their private files consistent
 * through capture, replace, delete, and launch-time crash recovery. UI code and the
 * CameraX capture controller both go through this -- neither touches the DAOs or
 * [EvidenceFileManager] directly.
 */
class EvidenceRepository(
    private val assessmentDraftDao: AssessmentDraftDao,
    private val taskDraftDao: TaskDraftDao,
    private val evidenceDraftDao: EvidenceDraftDao,
    private val fileManager: EvidenceFileManager,
    private val rules: Rules,
) {
    fun observeActiveAssessment(): Flow<AssessmentDraftEntity?> = assessmentDraftDao.observeActive()

    fun observeTasks(assessmentId: String): Flow<List<TaskDraftEntity>> = taskDraftDao.observeForAssessment(assessmentId)

    fun observeEvidenceForTask(assessmentId: String, taskId: String): Flow<List<EvidenceDraftEntity>> =
        evidenceDraftDao.observeForTask(assessmentId, taskId)

    suspend fun getActiveAssessment(): AssessmentDraftEntity? = assessmentDraftDao.getActiveOnce()

    fun resolveFile(evidence: EvidenceDraftEntity): File = fileManager.resolveRelativePath(evidence.relativePath)

    fun hasEnoughFreeSpace(): Boolean = fileManager.availableInternalBytes() >= EvidenceFileManager.MIN_FREE_BYTES_REQUIRED

    suspend fun createOrResumeAssessment(
        workerId: String?,
        language: String,
        matchOutput: MatchOutput?,
    ): AssessmentDraftEntity {
        assessmentDraftDao.getActiveOnce()?.let { return it }

        val now = System.currentTimeMillis()
        val gapIds = matchOutput?.applicableTasks
            ?.filter { it.extraEvidenceNeeded }
            ?.mapNotNull { it.task }
            ?.joinToString(",")
            .orEmpty()
        val assessment = AssessmentDraftEntity(
            id = UUID.randomUUID().toString(),
            state = AssessmentDraftState.ACTIVE,
            qpCode = rules.tasksFile.qpCode,
            qpVersion = rules.tasksFile.qpVersion,
            workerId = workerId,
            language = language,
            matchResult = matchOutput?.matchResult,
            overallCoverage = matchOutput?.overallCoverage,
            gapTaskIdsCsv = gapIds,
            isTestOnly = true,
            createdAtMillis = now,
            updatedAtMillis = now,
        )
        assessmentDraftDao.insert(assessment)
        taskDraftDao.insertAll(
            rules.tasksFile.tasks.map { task ->
                TaskDraftEntity(
                    assessmentId = assessment.id,
                    taskId = task.id,
                    state = TaskDraftState.NO_EVIDENCE,
                    evidenceCount = 0,
                    budgetBytes = task.budgetBytes,
                    capturedBytes = 0L,
                    updatedAtMillis = now,
                )
            },
        )
        return assessment
    }

    suspend fun beginCapture(
        assessmentId: String,
        taskId: String,
        kind: EvidenceType,
        debugOverrideRequested: Boolean,
        replacesEvidenceId: String? = null,
    ): BeginCaptureResult {
        if (!hasEnoughFreeSpace()) {
            Log.w(LOG_TAG, "begin_capture task=$taskId result=rejected reason=INSUFFICIENT_FREE_SPACE")
            return BeginCaptureResult.Rejected(CaptureRejectionReason.INSUFFICIENT_FREE_SPACE)
        }
        val info = ceilingInfo(assessmentId, taskId, debugOverrideRequested, replacesEvidenceId)
        if (info.remainingForTask <= 0L) {
            Log.w(LOG_TAG, "begin_capture task=$taskId result=rejected reason=TASK_BUDGET_EXHAUSTED")
            return BeginCaptureResult.Rejected(CaptureRejectionReason.TASK_BUDGET_EXHAUSTED)
        }
        if (info.remainingTotal <= 0L) {
            Log.w(LOG_TAG, "begin_capture task=$taskId result=rejected reason=TOTAL_BUDGET_EXHAUSTED")
            return BeginCaptureResult.Rejected(CaptureRejectionReason.TOTAL_BUDGET_EXHAUSTED)
        }

        val evidenceId = UUID.randomUUID().toString()
        val staging = fileManager.stagingFile(assessmentId, taskId, evidenceId, kind)
        val now = System.currentTimeMillis()
        evidenceDraftDao.insert(
            EvidenceDraftEntity(
                id = evidenceId,
                assessmentId = assessmentId,
                taskId = taskId,
                kind = kind,
                relativePath = fileManager.relativePathOf(staging),
                byteSize = 0L,
                createdAtMillis = now,
                widthPx = null,
                heightPx = null,
                durationMillis = null,
                state = EvidenceDraftState.STAGING,
                replacesEvidenceId = replacesEvidenceId,
                isTestOnly = true,
                debugCeilingRequested = debugOverrideRequested,
            ),
        )
        recomputeTaskDraft(assessmentId, taskId)
        Log.d(LOG_TAG, "begin_capture task=$taskId result=started ceilingBytes=${info.effective}")
        return BeginCaptureResult.Started(evidenceId, staging, info.effective)
    }

    /** Called by the capture screen/CameraX controller once a recording's measured bytes
     * reach the ceiling returned from [beginCapture], so UI and controller always agree
     * on the same number -- there is no second, independently-computed limit anywhere. */
    suspend fun currentCeilingBytes(
        assessmentId: String,
        taskId: String,
        debugOverrideRequested: Boolean,
        replacesEvidenceId: String? = null,
    ): Long = ceilingInfo(assessmentId, taskId, debugOverrideRequested, replacesEvidenceId).effective

    suspend fun finalizeCapture(
        evidenceId: String,
        success: Boolean,
        widthPx: Int? = null,
        heightPx: Int? = null,
        durationMillis: Long? = null,
    ): FinalizeResult {
        val row = evidenceDraftDao.getById(evidenceId) ?: return FinalizeResult.Failed
        val stagingFile = fileManager.resolveRelativePath(row.relativePath)

        if (!success) {
            fileManager.deleteQuietly(stagingFile)
            evidenceDraftDao.update(row.copy(state = EvidenceDraftState.FAILED, byteSize = 0L))
            recomputeTaskDraft(row.assessmentId, row.taskId)
            Log.w(LOG_TAG, "finalize_capture task=${row.taskId} result=failed category=capture_error")
            return FinalizeResult.Failed
        }

        // Never trust a caller-supplied size: the staging file CameraX/ImageCapture actually
        // wrote to disk is the only source of truth for what was captured. A missing staging
        // file after a reported "success" is itself treated as a failure, not a 0-byte READY.
        if (!stagingFile.exists()) {
            evidenceDraftDao.update(row.copy(state = EvidenceDraftState.FAILED, byteSize = 0L))
            recomputeTaskDraft(row.assessmentId, row.taskId)
            Log.w(LOG_TAG, "finalize_capture task=${row.taskId} result=failed category=staging_missing")
            return FinalizeResult.Failed
        }
        val actualBytes = stagingFile.length()

        // Fail-closed cap re-check, recomputed fresh against the CURRENT database state --
        // never the ceiling value computed back when this capture began (which is what the
        // live CameraX stop callback is allowed to overshoot slightly, by design -- see
        // [videoStopThresholdBytes]). No READY item may ever be retained above either its
        // task's or the assessment's real remaining budget, so this is the one place that
        // actually decides READY-worthiness; everything upstream is best-effort.
        val info = ceilingInfo(row.assessmentId, row.taskId, row.debugCeilingRequested, row.replacesEvidenceId)
        if (actualBytes > info.effective) {
            fileManager.deleteQuietly(stagingFile)
            evidenceDraftDao.update(row.copy(state = EvidenceDraftState.FAILED, byteSize = 0L))
            recomputeTaskDraft(row.assessmentId, row.taskId)
            Log.w(
                LOG_TAG,
                "finalize_capture task=${row.taskId} result=rejected category=over_limit " +
                    "actualBytes=$actualBytes allowedBytes=${info.effective}",
            )
            return FinalizeResult.RejectedOverLimit(actualBytes, info.effective)
        }

        val finalFile = fileManager.finalFile(row.assessmentId, row.taskId, row.id, row.kind)
        if (!fileManager.promote(stagingFile, finalFile)) {
            evidenceDraftDao.update(row.copy(state = EvidenceDraftState.FAILED, byteSize = 0L))
            recomputeTaskDraft(row.assessmentId, row.taskId)
            Log.w(LOG_TAG, "finalize_capture task=${row.taskId} result=failed category=promote_error")
            return FinalizeResult.Failed
        }

        // Re-stat the promoted file itself -- the only value ever written to the ledger is
        // what is actually sitting on disk under its final name, not a value computed
        // before the rename.
        val finalBytes = finalFile.length()
        if (finalBytes > info.effective) {
            // Defensive: a rename never changes a file's byte count on a single volume, so
            // this should be unreachable in practice, but the ledger must never trust an
            // assumption it can cheaply re-verify -- promotion is not yet visible to any
            // other reader (the row is still STAGING), so undoing it here is still safe.
            fileManager.deleteQuietly(finalFile)
            evidenceDraftDao.update(row.copy(state = EvidenceDraftState.FAILED, byteSize = 0L))
            recomputeTaskDraft(row.assessmentId, row.taskId)
            Log.w(
                LOG_TAG,
                "finalize_capture task=${row.taskId} result=rejected category=over_limit_post_promote " +
                    "actualBytes=$finalBytes allowedBytes=${info.effective}",
            )
            return FinalizeResult.RejectedOverLimit(finalBytes, info.effective)
        }

        val readyRow = row.copy(
            relativePath = fileManager.relativePathOf(finalFile),
            byteSize = finalBytes,
            widthPx = widthPx,
            heightPx = heightPx,
            durationMillis = durationMillis,
            state = EvidenceDraftState.READY,
        )
        evidenceDraftDao.update(readyRow)
        recomputeTaskDraft(row.assessmentId, row.taskId)
        Log.d(LOG_TAG, "finalize_capture task=${row.taskId} result=ready byteSize=$finalBytes")

        row.replacesEvidenceId?.let { oldId ->
            deleteEvidenceInternal(oldId)
            evidenceDraftDao.update(readyRow.copy(replacesEvidenceId = null))
        }
        return FinalizeResult.Ready(readyRow)
    }

    /** User backed out of an in-progress capture before it finalized: no evidence was ever
     * produced, so this leaves no trace (unlike a genuine finalize failure, which stays
     * visible as FAILED for the user to see and dismiss). */
    suspend fun cancelCapture(evidenceId: String) {
        val row = evidenceDraftDao.getById(evidenceId) ?: return
        fileManager.deleteQuietly(fileManager.resolveRelativePath(row.relativePath))
        evidenceDraftDao.hardDelete(row)
        recomputeTaskDraft(row.assessmentId, row.taskId)
    }

    suspend fun deleteEvidence(evidenceId: String) = deleteEvidenceInternal(evidenceId)

    suspend fun deleteAssessment(assessmentId: String) {
        assessmentDraftDao.getById(assessmentId)?.let {
            assessmentDraftDao.markDeleted(assessmentId, System.currentTimeMillis())
        }
        finishDeletingAssessment(assessmentId)
    }

    /** Runs once per process start, before any screen reads draft state. Closes every
     * crash-recovery window the rest of this class leaves open by design (mark-then-remove
     * for deletes, rename-then-commit for promotion, forward-recovery for replace), then
     * sweeps any file with no matching DB row at all. Safe to call repeatedly/idempotently. */
    suspend fun reconcileOnLaunch() {
        Log.d(LOG_TAG, "reconcile_on_launch result=started")
        assessmentDraftDao.listDeleted().forEach { finishDeletingAssessment(it.id) }

        evidenceDraftDao.listDeleted().forEach { row ->
            fileManager.deleteQuietly(fileManager.resolveRelativePath(row.relativePath))
            evidenceDraftDao.hardDelete(row)
        }

        val active = assessmentDraftDao.getActiveOnce()
        if (active != null) {
            evidenceDraftDao.getAllForAssessmentOnce(active.id)
                .filter { it.state == EvidenceDraftState.READY && it.replacesEvidenceId != null }
                .forEach { readyRow ->
                    val oldId = requireNotNull(readyRow.replacesEvidenceId)
                    if (evidenceDraftDao.getById(oldId) != null) {
                        deleteEvidenceInternal(oldId)
                    }
                    evidenceDraftDao.update(readyRow.copy(replacesEvidenceId = null))
                }
        }

        evidenceDraftDao.listStaging().forEach { row ->
            val finalFile = fileManager.finalFile(row.assessmentId, row.taskId, row.id, row.kind)
            if (finalFile.exists()) {
                evidenceDraftDao.update(
                    row.copy(relativePath = fileManager.relativePathOf(finalFile), byteSize = finalFile.length(), state = EvidenceDraftState.READY),
                )
            } else {
                fileManager.deleteQuietly(fileManager.resolveRelativePath(row.relativePath))
                evidenceDraftDao.update(row.copy(state = EvidenceDraftState.FAILED, byteSize = 0L))
            }
            recomputeTaskDraft(row.assessmentId, row.taskId)
        }

        sweepOrphanFiles()

        assessmentDraftDao.getActiveOnce()?.let { a ->
            taskDraftDao.getAllOnce(a.id).forEach { recomputeTaskDraft(a.id, it.taskId) }
        }
        Log.d(LOG_TAG, "reconcile_on_launch result=completed")
    }

    private suspend fun deleteEvidenceInternal(evidenceId: String) {
        val row = evidenceDraftDao.getById(evidenceId) ?: return
        if (row.state != EvidenceDraftState.DELETED) {
            evidenceDraftDao.markDeleted(evidenceId)
        }
        fileManager.deleteQuietly(fileManager.resolveRelativePath(row.relativePath))
        evidenceDraftDao.hardDelete(row)
        recomputeTaskDraft(row.assessmentId, row.taskId)
    }

    private suspend fun finishDeletingAssessment(assessmentId: String) {
        fileManager.deleteAssessmentTree(assessmentId)
        evidenceDraftDao.hardDeleteAllForAssessment(assessmentId)
        taskDraftDao.hardDeleteAllForAssessment(assessmentId)
        assessmentDraftDao.getById(assessmentId)?.let { assessmentDraftDao.hardDelete(it) }
    }

    private suspend fun sweepOrphanFiles() {
        val knownPaths = mutableSetOf<String>()
        assessmentDraftDao.getActiveOnce()?.let { active ->
            evidenceDraftDao.getAllForAssessmentOnce(active.id).forEach { knownPaths += it.relativePath }
        }
        for (assessmentDir in fileManager.listAssessmentDirs()) {
            for (taskDir in fileManager.listTaskDirs(assessmentDir.name)) {
                for (file in fileManager.listFilesIn(taskDir)) {
                    if (fileManager.relativePathOf(file) !in knownPaths) {
                        fileManager.deleteQuietly(file)
                    }
                }
            }
        }
    }

    private suspend fun recomputeTaskDraft(assessmentId: String, taskId: String) {
        val items = evidenceDraftDao.getAllForTaskOnce(assessmentId, taskId)
        val readyItems = items.filter { it.state == EvidenceDraftState.READY }
        val existing = taskDraftDao.getOne(assessmentId, taskId) ?: return
        taskDraftDao.update(
            existing.copy(
                state = computeTaskState(items),
                evidenceCount = readyItems.size,
                capturedBytes = readyItems.sumOf { it.byteSize },
                updatedAtMillis = System.currentTimeMillis(),
            ),
        )
    }

    private data class CeilingInfo(val remainingForTask: Long, val remainingTotal: Long, val effective: Long)

    private suspend fun ceilingInfo(
        assessmentId: String,
        taskId: String,
        debugOverrideRequested: Boolean,
        freeingEvidenceId: String?,
    ): CeilingInfo {
        val taskDraft = taskDraftDao.getOne(assessmentId, taskId)
        val taskBudget = taskDraft?.budgetBytes ?: 0L
        val allForAssessment = evidenceDraftDao.getAllForAssessmentOnce(assessmentId)
        val freedBytes = freeingEvidenceId
            ?.let { id -> allForAssessment.firstOrNull { it.id == id && it.state == EvidenceDraftState.READY }?.byteSize }
            ?: 0L
        val usedForTask = allForAssessment.filter { it.taskId == taskId && it.state == EvidenceDraftState.READY }.sumOf { it.byteSize }
        val usedTotal = allForAssessment.filter { it.state == EvidenceDraftState.READY }.sumOf { it.byteSize }
        val remainingForTask = (taskBudget - usedForTask + freedBytes).coerceAtLeast(0L)
        val remainingTotal = (rules.tasksFile.finalEvidenceBudgetBytes - usedTotal + freedBytes).coerceAtLeast(0L)
        var effective = minOf(remainingForTask, remainingTotal)
        if (BuildConfig.P4_TEST_ONLY_CEILING_ENABLED && debugOverrideRequested) {
            effective = minOf(effective, BuildConfig.P4_TEST_ONLY_CEILING_BYTES)
        }
        return CeilingInfo(remainingForTask, remainingTotal, effective)
    }

    companion object {
        fun computeTaskState(items: List<EvidenceDraftEntity>): TaskDraftState {
            if (items.any { it.state == EvidenceDraftState.STAGING }) return TaskDraftState.CAPTURING
            if (items.any { it.state == EvidenceDraftState.READY }) return TaskDraftState.READY
            if (items.any { it.state == EvidenceDraftState.FAILED }) return TaskDraftState.FAILED
            return TaskDraftState.NO_EVIDENCE
        }

        /** CameraX's [androidx.camera.video.VideoRecordEvent.Status] ticks are periodic, not
         * continuous -- by the time a caller's `Recording.stop()` call (issued from inside
         * that status callback) actually takes effect, more bytes beyond the last observed
         * tick have already been written to disk. The pre-fix P4 gate measured this real,
         * bounded overshoot on a real OnePlus 13R at roughly 24,300-29,857 bytes over a
         * 4,194,304-byte ceiling (~0.6-0.7%) and roughly 100 KB over a 15 MB task ceiling --
         * both single-digit-percent, not unbounded. Telling the recorder to stop at a
         * threshold already pulled back from the real ceiling by a guard band several times
         * larger than that observed overshoot (whichever of a fixed floor or a percentage of
         * the ceiling is larger, so the floor still means something for the smallest, 4 MiB
         * debug ceiling) absorbs that per-tick write burst in the overwhelming majority of
         * recordings. This guard band is a *quality-of-fit* optimization only, reducing how
         * often a capture needs to be rejected below -- the actual safety guarantee is the
         * fail-closed real-file-size check in [finalizeCapture], which rejects and deletes
         * any capture that still ends up over the real ceiling regardless of this threshold. */
        private const val VIDEO_GUARD_BAND_MIN_BYTES: Long = 192L * 1024
        private const val VIDEO_GUARD_BAND_PERCENT: Long = 3L

        fun videoStopThresholdBytes(ceilingBytes: Long): Long {
            if (ceilingBytes <= 0L) return 0L
            val guardBand = maxOf(VIDEO_GUARD_BAND_MIN_BYTES, ceilingBytes * VIDEO_GUARD_BAND_PERCENT / 100)
            return (ceilingBytes - guardBand).coerceAtLeast(1L)
        }
    }
}
