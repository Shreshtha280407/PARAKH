package `in`.kaushalpramaan.app.data.sync

import `in`.kaushalpramaan.app.data.draft.AppDatabase
import `in`.kaushalpramaan.app.data.draft.EvidenceFileManager
import `in`.kaushalpramaan.core.seal.VaultKeysetProvider
import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkRequest
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import java.util.concurrent.TimeUnit

/**
 * WorkManager entry point for P6 resumable sync -- see [SyncRepository] for the actual
 * upload orchestration this just wraps. Constructs its own dependencies directly from
 * [applicationContext] (same no-DI-framework pattern [in.kaushalpramaan.app.data.AppViewModel]
 * already uses for every other collaborator -- there is no custom Application/WorkerFactory
 * in this codebase, and adding one solely for this would be more machinery than the one
 * Worker class needs).
 */
class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val assessmentId = inputData.getString(KEY_ASSESSMENT_ID) ?: return Result.failure()
        val database = AppDatabase.getInstance(applicationContext)
        val repository = SyncRepository(
            assessmentDraftDao = database.assessmentDraftDao(),
            evidenceDraftDao = database.evidenceDraftDao(),
            outboxDao = database.outboxDao(),
            fileManager = EvidenceFileManager(applicationContext),
            vaultKeysetProvider = VaultKeysetProvider(applicationContext),
            endpointConfig = provideSyncEndpointConfig(applicationContext),
        )
        return when (val outcome = repository.syncAssessment(assessmentId)) {
            SyncRunOutcome.Success -> Result.success()
            is SyncRunOutcome.Retryable ->
                if (runAttemptCount < MAX_RETRY_ATTEMPTS) Result.retry() else Result.failure()
            is SyncRunOutcome.Terminal -> Result.failure()
        }
    }

    companion object {
        private const val KEY_ASSESSMENT_ID = "assessment_id"

        // A generous ceiling, not a realistic expectation: WorkManager's own exponential
        // backoff (capped at its own internal maximum delay) means this would take a very
        // long time to actually exhaust in practice -- it exists purely as a defensive upper
        // bound against an indefinitely-retrying job, not a target retry count.
        private const val MAX_RETRY_ATTEMPTS = 50

        fun uniqueWorkName(assessmentId: String, revisionId: String): String = "kp_sync_${assessmentId}_$revisionId"

        /** Enqueue (or, if this exact assessment/revision already has pending/running work,
         * leave the existing one alone -- [ExistingWorkPolicy.KEEP]) a sync attempt. Safe to
         * call repeatedly: from SealOrchestrator right after a real seal, from the launch-time
         * reconcile pass for an assessment that's already READY_TO_SYNC, and from a manual
         * "Sync now" tap -- none of these can ever produce two concurrent uploads of the same
         * revision. Once a previous attempt has actually finished (success OR a terminal
         * failure), KEEP no longer applies and a fresh call runs again from scratch -- exactly
         * the behaviour "Sync now" needs after a FAILED_ACTION_REQUIRED item is fixed by a new
         * seal (which also assigns a new revisionId, so it's a genuinely different unique
         * work name anyway). */
        fun enqueue(context: Context, assessmentId: String, revisionId: String) {
            val constraints = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
            val request = OneTimeWorkRequestBuilder<SyncWorker>()
                .setConstraints(constraints)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, WorkRequest.MIN_BACKOFF_MILLIS, TimeUnit.MILLISECONDS)
                .setInputData(workDataOf(KEY_ASSESSMENT_ID to assessmentId))
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork(
                uniqueWorkName(assessmentId, revisionId), ExistingWorkPolicy.KEEP, request,
            )
        }

        /** Stops a live upload immediately on discard/reopen -- defense in depth alongside
         * [SyncRepository.syncAssessment]'s own natural no-op once sealState leaves
         * READY_TO_SYNC (this just means the in-flight attempt doesn't have to wait for its
         * next network round-trip to notice). */
        fun cancel(context: Context, assessmentId: String, revisionId: String) {
            WorkManager.getInstance(context).cancelUniqueWork(uniqueWorkName(assessmentId, revisionId))
        }

        fun observeWorkInfo(context: Context, assessmentId: String, revisionId: String) =
            WorkManager.getInstance(context).getWorkInfosForUniqueWorkLiveData(uniqueWorkName(assessmentId, revisionId))
    }
}
