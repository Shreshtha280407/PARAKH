package `in`.kaushalpramaan.app.data.sync

import `in`.kaushalpramaan.app.data.draft.AppDatabase
import `in`.kaushalpramaan.app.data.draft.EvidenceFileManager
import `in`.kaushalpramaan.core.seal.VaultKeysetProvider
import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

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
        val startedAt = System.currentTimeMillis()
        setProgress(workDataOf(KEY_STARTED_AT to startedAt))
        fun failed(category: SyncErrorCategory, stage: String = "sync_request") = Result.failure(workDataOf(KEY_ERROR to category.name, KEY_STARTED_AT to startedAt, KEY_ERROR_STAGE to stage))
        val network = applicationContext.getSystemService(ConnectivityManager::class.java)
        val caps = network.getNetworkCapabilities(network.activeNetwork)
        if (caps?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) != true ||
            !caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)) {
            return failed(SyncErrorCategory.NETWORK_UNAVAILABLE, "connectivity_check")
        }
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
            SyncRunOutcome.Success -> Result.success(workDataOf(KEY_STARTED_AT to startedAt))
            // One attempt per seal or explicit Retry tap. A failed request must
            // never silently loop or restart merely because internet returns.
            is SyncRunOutcome.Retryable -> failed(outcome.category)
            is SyncRunOutcome.Terminal -> failed(outcome.category)
        }
    }

    companion object {
        private const val KEY_ASSESSMENT_ID = "assessment_id"
        const val KEY_STARTED_AT = "sync_started_at"
        const val KEY_ERROR = "sync_error"
        const val KEY_ERROR_STAGE = "sync_error_stage"

        fun uniqueWorkName(assessmentId: String, revisionId: String): String = "kp_sync_${assessmentId}_$revisionId"

        /** Low-level scheduling primitive. Automatic callers use [enqueueInitial]
         * so a failed attempt stays failed until the user requests [retryNow]. */
        fun enqueue(context: Context, assessmentId: String, revisionId: String) {
            enqueueWithPolicy(context, assessmentId, revisionId, ExistingWorkPolicy.KEEP)
        }

        /** Restart recovery may schedule an initial attempt that was interrupted
         * before enqueue, but never retries a completed/failed attempt. */
        suspend fun enqueueInitial(context: Context, assessmentId: String, revisionId: String) = withContext(Dispatchers.IO) {
            val manager = WorkManager.getInstance(context)
            val name = uniqueWorkName(assessmentId, revisionId)
            // Durable even after WorkManager prunes old finished jobs. Contains
            // only random local IDs, never names, media or server credentials.
            val once = context.getSharedPreferences("sync_initial_attempts", Context.MODE_PRIVATE)
            synchronized(initialEnqueueLock) {
                if (!once.getBoolean(name, false)) {
                    if (manager.getWorkInfosForUniqueWork(name).get().isEmpty()) {
                        enqueueWithPolicy(context, assessmentId, revisionId, ExistingWorkPolicy.KEEP).result.get()
                    }
                    check(once.edit().putBoolean(name, true).commit())
                }
            }
        }

        private val initialEnqueueLock = Any()

        private fun enqueueWithPolicy(context: Context, assessmentId: String, revisionId: String, policy: ExistingWorkPolicy): androidx.work.Operation {
            val request = OneTimeWorkRequestBuilder<SyncWorker>()
                .setInputData(workDataOf(KEY_ASSESSMENT_ID to assessmentId))
                .build()
            return WorkManager.getInstance(context).enqueueUniqueWork(
                uniqueWorkName(assessmentId, revisionId), policy, request,
            )
        }

        /** A manual retry replaces waiting/finished work. A visibly stalled
         * request can be explicitly restarted; ordinary duplicate taps preserve
         * a running upload. The repository serializes the cancellation race. */
        suspend fun retryNow(context: Context, assessmentId: String, revisionId: String, restartRunning: Boolean = false) = withContext(Dispatchers.IO) {
            val manager = WorkManager.getInstance(context)
            val running = manager.getWorkInfosForUniqueWork(uniqueWorkName(assessmentId, revisionId)).get()
                .any { it.state == androidx.work.WorkInfo.State.RUNNING }
            // An explicit new attempt should not reuse an idle connection the
            // server closed while the user was reading the failure message.
            // This closes only idle sockets; active uploads are unaffected.
            if (!running || restartRunning) SyncHttpClient.client.connectionPool.evictAll()
            enqueueWithPolicy(context, assessmentId, revisionId, if (running && !restartRunning) ExistingWorkPolicy.KEEP else ExistingWorkPolicy.REPLACE)
        }

        fun observeWorkInfoFlow(context: Context, assessmentId: String, revisionId: String) =
            WorkManager.getInstance(context).getWorkInfosForUniqueWorkFlow(uniqueWorkName(assessmentId, revisionId))

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
