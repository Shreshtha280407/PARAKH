package `in`.kaushalpramaan.app.data.sync

import `in`.kaushalpramaan.app.data.draft.AssessmentDraftDao
import `in`.kaushalpramaan.app.data.draft.AssessmentDraftEntity
import `in`.kaushalpramaan.app.data.draft.SealState
import `in`.kaushalpramaan.app.data.draft.TaskDraftDao
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private const val LOG_TAG = "KP-WorkerUpdates"

sealed class WorkerUpdatesPollResult {
    data class Applied(val updates: WorkerUpdatesOut) : WorkerUpdatesPollResult()
    data class Failed(val category: SyncErrorCategory) : WorkerUpdatesPollResult()
    data object NotYetSynced : WorkerUpdatesPollResult()
    data object NoActiveAssessment : WorkerUpdatesPollResult()
}

/**
 * P7: polls GET /assessments/{id}/worker-updates (durable, idempotent -- see
 * routers/reassessment.py::get_worker_updates) and applies the result to Room: per-task lock
 * state (every task except the ones the assessor reopened), the cached reason/capture-
 * instructions banner, and the report-availability flag. The sole writer of
 * TaskDraftEntity.locked and AssessmentDraftEntity's pending-reassessment, report-status, and
 * worker-updates-cursor columns.
 */
class WorkerUpdatesRepository(
    private val assessmentDraftDao: AssessmentDraftDao,
    private val taskDraftDao: TaskDraftDao,
    private val endpointConfig: SyncEndpointConfig,
) {
    suspend fun pollAndApply(assessmentId: String): WorkerUpdatesPollResult {
        val assessment = assessmentDraftDao.getById(assessmentId) ?: return WorkerUpdatesPollResult.NoActiveAssessment
        val serverAssessmentId = assessment.serverAssessmentId
        val workerToken = assessment.serverWorkerToken
        if (serverAssessmentId == null || workerToken == null) return WorkerUpdatesPollResult.NotYetSynced

        val apiClient = SyncApiClient(endpointConfig, workerToken)
        val updates = try {
            withContext(Dispatchers.IO) {
                apiClient.getWorkerUpdates(serverAssessmentId, assessment.workerUpdatesCursor)
            }
        } catch (e: SyncApiException) {
            Log.w(LOG_TAG, "poll result=failed category=${e.category}")
            return WorkerUpdatesPollResult.Failed(e.category)
        }
        applyUpdates(assessmentId, assessment, updates)
        Log.d(LOG_TAG, "poll result=applied reportStatus=${updates.reportStatus} pending=${updates.pendingReassessmentRequest != null}")
        return WorkerUpdatesPollResult.Applied(updates)
    }

    private suspend fun applyUpdates(assessmentId: String, assessment: AssessmentDraftEntity, updates: WorkerUpdatesOut) {
        val pending = updates.pendingReassessmentRequest
        val reopenedCodes = pending?.taskCodes?.toSet().orEmpty()
        // First time this exact request becomes visible on-device -- reopens the UI for
        // editing (see SealOrchestrator.sealTargetedRevision) and forces a fresh attestation
        // for the new capture, never silently reusing the OLD attestation timestamp for
        // genuinely new evidence.
        val previousReopenedCodes = assessment.pendingReassessmentTaskCodesCsv
            ?.split(",")?.filter { it.isNotBlank() }?.toSet().orEmpty()
        val isNewlyPending = pending != null &&
            (assessment.currentRevisionNumber != updates.revisionNumber || previousReopenedCodes != reopenedCodes)

        for (task in taskDraftDao.getAllOnce(assessmentId)) {
            val shouldLock = pending != null && task.taskId !in reopenedCodes
            if (task.locked != shouldLock) {
                taskDraftDao.update(task.copy(locked = shouldLock))
            }
        }

        assessmentDraftDao.update(
            assessment.copy(
                pendingReassessmentTaskCodesCsv = pending?.taskCodes?.joinToString(","),
                pendingReassessmentReason = pending?.reason,
                pendingReassessmentCaptureInstructions = pending?.captureInstructions,
                currentRevisionNumber = updates.revisionNumber,
                reportStatus = updates.reportStatus,
                // Advanced only now that the update has actually been applied to every row
                // above -- a crash between the server response and this write replays safely
                // on the next poll instead of silently skipping the update.
                workerUpdatesCursor = maxOf(assessment.workerUpdatesCursor, updates.latestEventId),
                sealState = if (isNewlyPending) SealState.DRAFT_EDITABLE else assessment.sealState,
                attestationConfirmed = if (isNewlyPending) false else assessment.attestationConfirmed,
                attestationAtMillis = if (isNewlyPending) null else assessment.attestationAtMillis,
            ),
        )
    }
}
