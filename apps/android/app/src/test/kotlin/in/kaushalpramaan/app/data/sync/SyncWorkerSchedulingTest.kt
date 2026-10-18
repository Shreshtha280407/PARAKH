package `in`.kaushalpramaan.app.data.sync

import android.content.Context
import android.os.Looper
import androidx.test.core.app.ApplicationProvider
import androidx.work.*
import androidx.work.testing.SynchronousExecutor
import androidx.work.testing.WorkManagerTestInitHelper
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf

/** Real scheduler/offline-worker tests for one initial attempt and manual retry. */
@RunWith(RobolectricTestRunner::class)
class SyncWorkerSchedulingTest {
    private lateinit var context: Context
    private lateinit var manager: WorkManager
    @Before fun setup() {
        context = ApplicationProvider.getApplicationContext()
        context.getSharedPreferences("sync_initial_attempts", Context.MODE_PRIVATE).edit().clear().commit()
        initialize()
    }
    private fun initialize(factory: WorkerFactory? = null) {
        val config = Configuration.Builder().setExecutor(SynchronousExecutor()).apply { if (factory != null) setWorkerFactory(factory) }.build()
        WorkManagerTestInitHelper.initializeTestWorkManager(context, config)
        manager = WorkManager.getInstance(context)
    }
    private fun infos(rev: String = "rev") = manager.getWorkInfosForUniqueWork(SyncWorker.uniqueWorkName("assessment", rev)).get()
    private fun awaitState(state: WorkInfo.State, rev: String = "rev") {
        val deadline = System.currentTimeMillis() + 10_000
        while (infos(rev).none { it.state == state } && System.currentTimeMillis() < deadline) {
            shadowOf(Looper.getMainLooper()).idle(); Thread.sleep(10)
        }
        assertTrue("Expected $state, got ${infos(rev).map { it.state }}", infos(rev).any { it.state == state })
    }
    @Test fun initialOfflineAttemptFailsWithSafeErrorAndDoesNotScheduleBackoff() = runBlocking {
        SyncWorker.enqueueInitial(context, "assessment", "rev"); awaitState(WorkInfo.State.FAILED)
        assertEquals(SyncErrorCategory.NETWORK_UNAVAILABLE.name, infos().single().outputData.getString(SyncWorker.KEY_ERROR))
        assertEquals("connectivity_check", infos().single().outputData.getString(SyncWorker.KEY_ERROR_STAGE))
        assertEquals(1, infos().single().runAttemptCount)
    }
    @Test fun repeatedAutomaticTriggersDoNotRestartTheFailedAttempt() = runBlocking {
        SyncWorker.enqueueInitial(context, "assessment", "rev"); awaitState(WorkInfo.State.FAILED)
        val original = infos().single().id
        repeat(3) { SyncWorker.enqueueInitial(context, "assessment", "rev") }
        assertEquals(original, infos().single().id)
        assertEquals(1, infos().single().runAttemptCount)
    }
    @Test fun explicitRetryStartsANewAttemptAfterFailure() = runBlocking {
        SyncWorker.enqueueInitial(context, "assessment", "rev"); awaitState(WorkInfo.State.FAILED)
        val original = infos().single().id
        SyncWorker.retryNow(context, "assessment", "rev")
        val deadline = System.currentTimeMillis() + 10_000
        while (infos().none { it.id != original && it.state == WorkInfo.State.FAILED } && System.currentTimeMillis() < deadline) {
            shadowOf(Looper.getMainLooper()).idle(); Thread.sleep(10)
        }
        assertTrue(infos().any { it.id != original && it.state == WorkInfo.State.FAILED })
    }
    @Test fun newRevisionGetsItsOwnFirstAutomaticAttempt() = runBlocking {
        SyncWorker.enqueueInitial(context, "assessment", "rev"); awaitState(WorkInfo.State.FAILED)
        SyncWorker.enqueueInitial(context, "assessment", "revision-2"); awaitState(WorkInfo.State.FAILED, "revision-2")
        assertNotEquals(infos().single().id, infos("revision-2").single().id)
    }
    @Test fun manualRetryDoesNotDuplicateARunningUpload() = runBlocking {
        initialize(object : WorkerFactory() {
            override fun createWorker(appContext: Context, workerClassName: String, workerParameters: WorkerParameters): ListenableWorker =
                object : CoroutineWorker(appContext, workerParameters) { override suspend fun doWork(): Result = awaitCancellation() }
        })
        SyncWorker.enqueueInitial(context, "assessment", "rev"); awaitState(WorkInfo.State.RUNNING)
        val original = infos().single().id
        SyncWorker.retryNow(context, "assessment", "rev")
        assertEquals(original, infos().single().id)
        SyncWorker.cancel(context, "assessment", "rev"); awaitState(WorkInfo.State.CANCELLED)
    }
    @Test fun firstAttemptFlagSurvivesPrunedWorkHistory() = runBlocking {
        context.getSharedPreferences("sync_initial_attempts", Context.MODE_PRIVATE).edit()
            .putBoolean(SyncWorker.uniqueWorkName("assessment", "rev"), true).commit()
        SyncWorker.enqueueInitial(context, "assessment", "rev")
        assertTrue(infos().isEmpty())
    }
}
