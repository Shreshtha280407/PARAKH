package `in`.kaushalpramaan.app.data.assistance

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.work.*
import androidx.work.testing.SynchronousExecutor
import androidx.work.testing.WorkManagerTestInitHelper
import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.data.draft.*
import `in`.kaushalpramaan.core.mapping.RulesLoader
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** Real WorkManager bookkeeping, real Room identities, no native inference. The worker
 * body is covered separately by AssistanceRunner and physical integration instrumentation. */
@RunWith(RobolectricTestRunner::class)
class AssistanceSchedulingTest {
    private lateinit var db: AppDatabase
    private lateinit var files: EvidenceFileManager
    private lateinit var coordinator: EvidenceAssistanceCoordinator
    private lateinit var item: EvidenceDraftEntity
    private lateinit var wm: WorkManager
    @Before fun prepare() = runBlocking {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val config = Configuration.Builder().setExecutor(SynchronousExecutor()).setWorkerFactory(object : WorkerFactory() {
            override fun createWorker(appContext: Context, workerClassName: String, workerParameters: WorkerParameters): ListenableWorker =
                object : CoroutineWorker(appContext, workerParameters) { override suspend fun doWork() = Result.success() }
        }).build()
        WorkManagerTestInitHelper.initializeTestWorkManager(context, config)
        wm = WorkManager.getInstance(context)
        db = Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java).allowMainThreadQueries().build()
        files = object : EvidenceFileManager(context) { override fun availableInternalBytes() = 10L * 1024 * 1024 * 1024 }
        val repo = EvidenceRepository(db.assessmentDraftDao(), db.taskDraftDao(), db.evidenceDraftDao(), files, RulesLoader.load())
        val a = repo.createOrResumeAssessment("TEST", "en", null)
        val begin = repo.beginCapture(a.id, "T1", EvidenceType.PHOTO, false) as BeginCaptureResult.Started
        begin.stagingFile.writeBytes(byteArrayOf(1, 2, 3))
        item = (repo.finalizeCapture(begin.evidenceId, true) as FinalizeResult.Ready).evidence
        coordinator = EvidenceAssistanceCoordinator(context, db, files)
    }
    @After fun close() { wm.cancelAllWork().result.get(); db.close() }
    @Test fun repeated_schedule_deduplicates_and_never_requires_network() = runBlocking {
        coordinator.schedule(item.id)
        val first = db.assistanceDao().get(item.id)!!
        coordinator.schedule(item.id)
        assertEquals(first.generation, db.assistanceDao().get(item.id)!!.generation)
        val infos = wm.getWorkInfosForUniqueWork(EvidenceAssistanceCoordinator.tag(item.id)).get()
        assertEquals(1, infos.size)
        assertEquals(NetworkType.NOT_REQUIRED, infos.single().constraints.requiredNetworkType)
        assertEquals("QUEUED", first.status)
    }
    @Test fun retry_changes_generation_and_cancellation_is_durable() = runBlocking {
        coordinator.schedule(item.id)
        val generation = db.assistanceDao().get(item.id)!!.generation
        coordinator.schedule(item.id, retry = true)
        assertNotEquals(generation, db.assistanceDao().get(item.id)!!.generation)
        coordinator.cancel(item.id)
        assertEquals("NOT_RUN", db.assistanceDao().get(item.id)!!.status)
        assertEquals("CANCELLED", db.assistanceDao().get(item.id)!!.errorCategory)
    }
    @Test fun unchanged_final_bytes_reuse_completed_result_but_new_bytes_queue_fresh_analysis() = runBlocking {
        coordinator.schedule(item.id)
        val original = db.assistanceDao().get(item.id)!!
        db.assistanceDao().put(original.copy(status = "COMPLETED", stage = "finished"))
        val finalFile = java.io.File(files.resolveRelativePath(item.relativePath).parentFile, "final.jpg")
        files.resolveRelativePath(item.relativePath).copyTo(finalFile)
        db.evidenceDraftDao().update(item.copy(finalState = FinalEvidenceState.OPTIMIZED, finalRelativePath = files.relativePathOf(finalFile)))
        coordinator.schedule(item.id)
        assertEquals(original.generation, db.assistanceDao().get(item.id)!!.generation)
        finalFile.appendBytes(byteArrayOf(4))
        coordinator.schedule(item.id)
        assertNotEquals(original.generation, db.assistanceDao().get(item.id)!!.generation)
        assertEquals("QUEUED", db.assistanceDao().get(item.id)!!.status)
    }
    @Test fun sealed_or_deleted_evidence_cannot_schedule_or_retry() = runBlocking {
        val a = db.assessmentDraftDao().getById(item.assessmentId)!!
        db.assessmentDraftDao().update(a.copy(sealState = SealState.SEAL_IN_PROGRESS))
        coordinator.schedule(item.id, retry = true)
        assertNull(db.assistanceDao().get(item.id))
        db.evidenceDraftDao().markDeleted(item.id)
        coordinator.schedule(item.id, retry = true)
        assertNull(db.assistanceDao().get(item.id))
    }
    @Test fun missing_video_duration_is_unavailable_until_container_metadata_is_recovered() = runBlocking {
        db.evidenceDraftDao().update(item.copy(kind = EvidenceType.VIDEO))
        coordinator.schedule(item.id)
        val unavailable = db.assistanceDao().get(item.id)!!
        assertEquals("UNAVAILABLE", unavailable.status)
        assertEquals("MEDIA_UNAVAILABLE", unavailable.errorCategory)
        assertTrue(wm.getWorkInfosForUniqueWork(EvidenceAssistanceCoordinator.tag(item.id)).get().isEmpty())
        db.evidenceDraftDao().update(item.copy(kind = EvidenceType.VIDEO, durationMillis = 2000))
        coordinator.schedule(item.id)
        assertEquals("QUEUED", db.assistanceDao().get(item.id)!!.status)
        assertNotEquals(unavailable.generation, db.assistanceDao().get(item.id)!!.generation)
    }
    @Test fun concurrent_retries_leave_the_latest_durable_generation_scheduled() = runBlocking {
        coroutineScope {
            (1..16).map { async(Dispatchers.Default) { coordinator.schedule(item.id, retry = true) } }.awaitAll()
        }
        val generation = db.assistanceDao().get(item.id)!!.generation
        val infos = wm.getWorkInfosForUniqueWork(EvidenceAssistanceCoordinator.tag(item.id)).get()
        assertTrue("Room's latest generation must have live or succeeded work", infos.any {
            generation in it.tags && it.state != WorkInfo.State.CANCELLED
        })
    }
}
