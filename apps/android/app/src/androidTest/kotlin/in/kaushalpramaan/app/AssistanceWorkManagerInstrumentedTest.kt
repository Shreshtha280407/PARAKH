package `in`.kaushalpramaan.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.work.*
import androidx.work.testing.WorkManagerTestInitHelper
import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.data.assistance.*
import `in`.kaushalpramaan.app.data.draft.*
import `in`.kaushalpramaan.core.mapping.RulesLoader
import `in`.kaushalpramaan.core.seal.StreamingHasher
import `in`.kaushalpramaan.media.VideoOptimizer
import java.util.concurrent.Executors
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Real production worker and native engines, with only its database dependency
 * supplied by a WorkerFactory. WorkManager's test DB is in memory; kp_drafts.db and
 * production WorkManager jobs are never modified/cancelled. No fake worker body. */
@RunWith(AndroidJUnit4::class)
class AssistanceWorkManagerInstrumentedTest {
    @Test fun production_post_capture_jobs_run_real_inference_in_isolated_encrypted_storage() = runBlocking {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val name = "p8-workmanager-${System.nanoTime()}.db"
        val db = AppDatabase.build(context, name)
        val files = EvidenceFileManager(context)
        val executor = Executors.newFixedThreadPool(2)
        val configuration = Configuration.Builder().setExecutor(executor).setWorkerFactory(object : WorkerFactory() {
            override fun createWorker(appContext: Context, workerClassName: String, workerParameters: WorkerParameters): ListenableWorker? =
                if (workerClassName == EvidenceAssistanceWorker::class.java.name)
                    EvidenceAssistanceWorker(appContext, workerParameters, db) else null
        }).build()
        WorkManagerTestInitHelper.initializeTestWorkManager(context, configuration)
        val wm = WorkManager.getInstance(context)
        val coordinator = EvidenceAssistanceCoordinator(context, db, files)
        val repository = EvidenceRepository(db.assessmentDraftDao(), db.taskDraftDao(), db.evidenceDraftDao(),
            files, RulesLoader.load(), assistance = coordinator)
        val assessment = repository.createOrResumeAssessment("P8-SYNTHETIC-WORKMANAGER", "en", null)
        val ids = mutableListOf<String>()
        try {
            val photo = repository.beginCapture(assessment.id, "T1", EvidenceType.PHOTO, false) as BeginCaptureResult.Started
            ids += photo.evidenceId
            Bitmap.createBitmap(320, 240, Bitmap.Config.ARGB_8888).apply {
                eraseColor(Color.BLACK)
                photo.stagingFile.outputStream().use { assertTrue(compress(Bitmap.CompressFormat.JPEG, 95, it)) }
                recycle()
            }
            assertTrue(repository.finalizeCapture(photo.evidenceId, true, 320, 240) is FinalizeResult.Ready)
            val video = repository.beginCapture(assessment.id, "T2", EvidenceType.VIDEO, false) as BeginCaptureResult.Started
            ids += video.evidenceId
            instrumentation.context.assets.open("fixtures/synthetic-rotation90.mp4").use { input ->
                video.stagingFile.outputStream().use { input.copyTo(it) }
            }
            val metadata = VideoOptimizer(context).validateContainer(video.stagingFile)!!
            assertTrue(repository.finalizeCapture(video.evidenceId, true, metadata.widthPx, metadata.heightPx, metadata.durationMs) is FinalizeResult.Ready)
            val hashes = ids.associateWith { StreamingHasher.sha256Hex(repository.resolveFile(db.evidenceDraftDao().getById(it)!!)) }
            withTimeout(90_000) {
                while (ids.any { db.assistanceDao().get(it)?.status !in setOf("COMPLETED", "PARTIAL") }) delay(50)
                while (ids.any { wm.getWorkInfosForUniqueWork(EvidenceAssistanceCoordinator.tag(it)).get().none { w -> w.state == WorkInfo.State.SUCCEEDED } }) delay(50)
            }
            assertTrue(db.assistanceDao().get(photo.evidenceId)!!.resultJson!!.contains("DARK"))
            assertTrue(db.assistanceDao().get(video.evidenceId)!!.resultJson!!.contains("modelSha256"))
            for (id in ids) {
                assertEquals(hashes[id], StreamingHasher.sha256Hex(repository.resolveFile(db.evidenceDraftDao().getById(id)!!)))
                val generation = db.assistanceDao().get(id)!!.generation
                coordinator.schedule(id)
                assertEquals(generation, db.assistanceDao().get(id)!!.generation)
                val info = wm.getWorkInfosForUniqueWork(EvidenceAssistanceCoordinator.tag(id)).get().single()
                assertEquals(WorkInfo.State.SUCCEEDED, info.state)
                assertEquals(NetworkType.NOT_REQUIRED, info.constraints.requiredNetworkType)
            }
        } finally {
            ids.forEach { wm.cancelUniqueWork(EvidenceAssistanceCoordinator.tag(it)).result.get() }
            WorkManagerTestInitHelper.closeWorkDatabase()
            executor.shutdownNow()
            files.deleteAssessmentTree(assessment.id); db.close(); context.deleteDatabase(name)
        }
    }
}
