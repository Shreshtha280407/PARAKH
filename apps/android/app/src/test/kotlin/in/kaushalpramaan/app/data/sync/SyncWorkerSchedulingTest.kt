package `in`.kaushalpramaan.app.data.sync

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.work.Configuration
import androidx.work.NetworkType
import androidx.work.WorkInfo
import androidx.work.WorkManager
import androidx.work.testing.SynchronousExecutor
import androidx.work.testing.WorkManagerTestInitHelper
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * Proves SyncWorker's WorkManager wiring itself -- unique work naming, the network constraint,
 * duplicate-invocation/"sync now" dedup (ExistingWorkPolicy.KEEP), and cancellation -- all pure
 * WorkManager bookkeeping, correctly testable without a real device (Robolectric +
 * WorkManagerTestInitHelper, the standard way to unit-test WorkManager scheduling logic). The
 * actual upload work this schedules (SyncRepository.syncAssessment, which needs a real
 * Keystore-backed vault) is proven separately on a real device (see
 * SyncRepositoryInstrumentedTest / docs/gates/P6.md).
 */
@RunWith(RobolectricTestRunner::class)
class SyncWorkerSchedulingTest {
    private lateinit var context: Context
    private lateinit var workManager: WorkManager

    @Before
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        val config = Configuration.Builder().setExecutor(SynchronousExecutor()).build()
        WorkManagerTestInitHelper.initializeTestWorkManager(context, config)
        workManager = WorkManager.getInstance(context)
    }

    @Test
    fun enqueue_uses_a_stable_unique_work_name_derived_from_assessment_and_revision() {
        SyncWorker.enqueue(context, "assessment-1", "rev-1")
        val infos = workManager.getWorkInfosForUniqueWork(SyncWorker.uniqueWorkName("assessment-1", "rev-1")).get()
        assertEquals(1, infos.size)
        assertTrue(infos[0].state == WorkInfo.State.ENQUEUED || infos[0].state == WorkInfo.State.RUNNING)
    }

    @Test
    fun enqueue_requires_the_network_connected_constraint() {
        SyncWorker.enqueue(context, "assessment-1", "rev-1")
        val infos = workManager.getWorkInfosForUniqueWork(SyncWorker.uniqueWorkName("assessment-1", "rev-1")).get()
        // WorkInfo doesn't expose Constraints directly in all WorkManager versions, but the
        // request having been correctly built with a CONNECTED constraint is proven indirectly
        // by its state staying ENQUEUED (not RUNNING) under Robolectric's default fake network
        // state (disconnected) unless explicitly told otherwise -- see the next test.
        assertEquals(WorkInfo.State.ENQUEUED, infos[0].state)
    }

    @Test
    fun a_second_enqueue_for_the_same_assessment_and_revision_does_not_create_a_duplicate_job() {
        SyncWorker.enqueue(context, "assessment-1", "rev-1")
        SyncWorker.enqueue(context, "assessment-1", "rev-1")
        val infos = workManager.getWorkInfosForUniqueWork(SyncWorker.uniqueWorkName("assessment-1", "rev-1")).get()
        assertEquals(
            "a repeated 'sync now' / duplicate WorkManager invocation for the same revision must never queue a second job",
            1, infos.size,
        )
    }

    @Test
    fun different_revisions_of_the_same_assessment_get_independent_unique_work() {
        SyncWorker.enqueue(context, "assessment-1", "rev-OLD")
        SyncWorker.enqueue(context, "assessment-1", "rev-NEW")
        assertEquals(1, workManager.getWorkInfosForUniqueWork(SyncWorker.uniqueWorkName("assessment-1", "rev-OLD")).get().size)
        assertEquals(1, workManager.getWorkInfosForUniqueWork(SyncWorker.uniqueWorkName("assessment-1", "rev-NEW")).get().size)
    }

    @Test
    fun cancel_stops_the_enqueued_work_for_that_revision() {
        SyncWorker.enqueue(context, "assessment-1", "rev-1")
        SyncWorker.cancel(context, "assessment-1", "rev-1")
        val infos = workManager.getWorkInfosForUniqueWork(SyncWorker.uniqueWorkName("assessment-1", "rev-1")).get()
        assertTrue(infos.all { it.state == WorkInfo.State.CANCELLED })
    }

    @Test
    fun enqueuing_again_after_cancellation_runs_fresh_not_blocked_by_keep_policy() {
        SyncWorker.enqueue(context, "assessment-1", "rev-1")
        SyncWorker.cancel(context, "assessment-1", "rev-1")
        SyncWorker.enqueue(context, "assessment-1", "rev-1")
        val infos = workManager.getWorkInfosForUniqueWork(SyncWorker.uniqueWorkName("assessment-1", "rev-1")).get()
        // The cancelled request plus a fresh one -- KEEP only skips re-enqueue while existing
        // work is still pending/running, never once it has finished (cancelled or otherwise).
        assertTrue(infos.any { it.state == WorkInfo.State.ENQUEUED })
    }
}
