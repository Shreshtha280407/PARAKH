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
        actualByteSize: Long = 0L,
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

        val finalFile = fileManager.finalFile(row.assessmentId, row.taskId, row.id, row.kind)
        if (!fileManager.promote(stagingFile, finalFile)) {
            evidenceDraftDao.update(row.copy(state = EvidenceDraftState.FAILED, byteSize = 0L))
            recomputeTaskDraft(row.assessmentId, row.taskId)
            Log.w(LOG_TAG, "finalize_capture task=${row.taskId} result=failed category=promote_error")
            return FinalizeResult.Failed
        }

        val readyRow = row.copy(
            relativePath = fileManager.relativePathOf(finalFile),
            byteSize = actualByteSize,
            widthPx = widthPx,
            heightPx = heightPx,
            durationMillis = durationMillis,
            state = EvidenceDraftState.READY,
        )
        evidenceDraftDao.update(readyRow)
        recomputeTaskDraft(row.assessmentId, row.taskId)
        Log.d(LOG_TAG, "finalize_capture task=${row.taskId} result=ready byteSize=$actualByteSize")

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
    }
}
