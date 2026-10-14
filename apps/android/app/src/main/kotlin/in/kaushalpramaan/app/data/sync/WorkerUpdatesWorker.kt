package `in`.kaushalpramaan.app.data.sync

import `in`.kaushalpramaan.app.data.draft.AppDatabase
import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import java.util.concurrent.TimeUnit

/**
 * P7: periodic WorkManager poll for the durable worker-updates feed (reassessment requests,
 * report availability) -- see [WorkerUpdatesRepository]. 15 minutes is the Android platform
 * floor for periodic work ([androidx.work.PeriodicWorkRequest.MIN_PERIODIC_INTERVAL_MILLIS]);
 * a manual "Check for updates" action (AppViewModel.checkForWorkerUpdates) exists for an
 * immediate, on-demand pull and uses the exact same [WorkerUpdatesRepository] logic.
 */
class WorkerUpdatesWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val assessmentId = inputData.getString(KEY_ASSESSMENT_ID) ?: return Result.failure()
        val database = AppDatabase.getInstance(applicationContext)
        val repository = WorkerUpdatesRepository(
            assessmentDraftDao = database.assessmentDraftDao(),
            taskDraftDao = database.taskDraftDao(),
            endpointConfig = provideSyncEndpointConfig(applicationContext),
        )
        return when (repository.pollAndApply(assessmentId)) {
            is WorkerUpdatesPollResult.Applied, WorkerUpdatesPollResult.NoActiveAssessment, WorkerUpdatesPollResult.NotYetSynced ->
                Result.success()
            is WorkerUpdatesPollResult.Failed -> Result.retry()
        }
    }

    companion object {
        private const val KEY_ASSESSMENT_ID = "assessment_id"

        private fun uniqueWorkName(assessmentId: String) = "kp_worker_updates_$assessmentId"

        /** Starts (or leaves alone, if already running -- [ExistingPeriodicWorkPolicy.KEEP])
         * periodic polling for this assessment. Safe to call every time the app resumes a
         * draft that has already bootstrapped server identity -- polling an assessment with
         * nothing pending is a cheap, idempotent no-op server-side. */
        fun enqueuePeriodic(context: Context, assessmentId: String) {
            val constraints = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
            val request = PeriodicWorkRequestBuilder<WorkerUpdatesWorker>(15, TimeUnit.MINUTES)
                .setConstraints(constraints)
                .setInputData(workDataOf(KEY_ASSESSMENT_ID to assessmentId))
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                uniqueWorkName(assessmentId), ExistingPeriodicWorkPolicy.KEEP, request,
            )
        }

        fun cancel(context: Context, assessmentId: String) {
            WorkManager.getInstance(context).cancelUniqueWork(uniqueWorkName(assessmentId))
        }
    }
}
