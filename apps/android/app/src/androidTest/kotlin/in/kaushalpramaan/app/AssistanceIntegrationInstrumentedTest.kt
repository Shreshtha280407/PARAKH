package `in`.kaushalpramaan.app

import android.graphics.Bitmap
import android.graphics.Color
import android.util.Base64
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.data.assistance.*
import `in`.kaushalpramaan.app.data.draft.*
import `in`.kaushalpramaan.app.data.seal.*
import `in`.kaushalpramaan.core.mapping.RulesLoader
import `in`.kaushalpramaan.core.seal.*
import `in`.kaushalpramaan.media.*
import java.io.File
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Uses isolated SQLCipher DB/files and a unique signing alias. Never clears app data,
 * touches another assessment or imports private recordings. Not field accuracy evidence. */
@RunWith(AndroidJUnit4::class)
class AssistanceIntegrationInstrumentedTest {
    @Test fun production_package_has_no_mediapipe_telemetry_upload_components() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val info = context.packageManager.getPackageInfo(context.packageName,
            android.content.pm.PackageManager.GET_SERVICES or android.content.pm.PackageManager.GET_RECEIVERS)
        val components = info.services.orEmpty().map { it.name } + info.receivers.orEmpty().map { it.name }
        assertFalse(components.any { it.startsWith("com.google.android.datatransport.") })
    }
    private fun verifyRequestedOfflineRun() {
        if (InstrumentationRegistry.getArguments().getString("p8RequireOffline") == "true") {
            val connectivity = InstrumentationRegistry.getInstrumentation().targetContext
                .getSystemService(ConnectivityManager::class.java)
            fun hasInternetNetwork() = connectivity.allNetworks.any {
                connectivity.getNetworkCapabilities(it)?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true
            }
            // Android disconnects asynchronously after an airplane/data toggle. Wait
            // for the actual condition, then fail rather than weakening offline proof.
            val deadline = android.os.SystemClock.elapsedRealtime() + 30_000
            while (hasInternetNetwork() && android.os.SystemClock.elapsedRealtime() < deadline) android.os.SystemClock.sleep(100)
            assertFalse("Offline proof requires no network with INTERNET capability", hasInternetNetwork())
        }
    }

    @Test fun bundled_mediapipe_and_quality_analyse_private_video_without_rewriting_media() = runBlocking {
        verifyRequestedOfflineRun()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val name = "p8-video-${System.nanoTime()}.db"
        val db = AppDatabase.build(context, name)
        val files = EvidenceFileManager(context)
        val repo = EvidenceRepository(db.assessmentDraftDao(), db.taskDraftDao(), db.evidenceDraftDao(), files, RulesLoader.load())
        val a = repo.createOrResumeAssessment("P8-SYNTHETIC-VIDEO", "en", null)
        try {
            val begin = repo.beginCapture(a.id, "T2", EvidenceType.VIDEO, false) as BeginCaptureResult.Started
            instrumentation.context.assets.open("fixtures/synthetic-rotation90.mp4").use { input -> begin.stagingFile.outputStream().use { input.copyTo(it) } }
            val metadata = VideoOptimizer(context).validateContainer(begin.stagingFile)!!
            // Missing capture metadata must not turn assistance into a P5 submission gate.
            val captured = (repo.finalizeCapture(begin.evidenceId, true) as FinalizeResult.Ready).evidence
            assertNull(captured.durationMillis)
            val processing = SealOrchestrator(db.assessmentDraftDao(), db.evidenceDraftDao(), db.outboxDao(), files, RulesLoader.load(),
                PhotoOptimizer(), VideoOptimizer(context), VaultKeysetProvider(context), "p8-video-metadata", "p8-video-${System.nanoTime()}")
            assertEquals(ProcessOutcome.AllFit, processing.processEvidence(a.id))
            val item = db.evidenceDraftDao().getById(captured.id)!!
            assertEquals(metadata.durationMs, item.finalDurationMillis)
            val input = files.resolveRelativePath(EvidenceAssistanceCoordinator.inputPath(item))
            val hash = StreamingHasher.sha256Hex(input)
            db.assistanceDao().put(AssistanceRecord(item.id, a.id, "T2", 1, "native-video", EvidenceAssistanceCoordinator.inputPath(item),
                hash, metadata.durationMs, "QUEUED", "queued", null, null, null))
            AssistanceRunner(db, files, OnDeviceAssistance(context)).run(item.id, "native-video")
            val result = EvidenceAssistanceCoordinator.JSON.decodeFromString<AssistanceSnapshot>(db.assistanceDao().get(item.id)!!.resultJson!!)
            assertTrue(result.status in setOf(AssistanceStatus.COMPLETED, AssistanceStatus.PARTIAL))
            assertTrue(result.hands!!.coverage.analysedSamples > 0)
            assertNotNull(result.hands!!.provenance!!.modelSha256)
            assertTrue(result.flags.all { it.endMs == null || it.endMs!! <= metadata.durationMs })
            assertEquals(hash, StreamingHasher.sha256Hex(input))
        } finally { files.deleteAssessmentTree(a.id); files.deleteP5TempTree(a.id); db.close(); context.deleteDatabase(name) }
    }

    @Test fun real_offline_analysis_survives_db_reopen_and_is_signed_with_final_evidence() = runBlocking {
        verifyRequestedOfflineRun()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val name = "p8-instrumentation-${System.nanoTime()}.db"
        var db = AppDatabase.build(context, name)
        val files = EvidenceFileManager(context)
        val rules = RulesLoader.load()
        val repo = EvidenceRepository(db.assessmentDraftDao(), db.taskDraftDao(), db.evidenceDraftDao(), files, rules)
        val a = repo.createOrResumeAssessment("P8-SYNTHETIC", "en", null)
        try {
            val capture = repo.beginCapture(a.id, "T1", EvidenceType.PHOTO, false) as BeginCaptureResult.Started
            val image = Bitmap.createBitmap(320, 240, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.BLACK) }
            capture.stagingFile.outputStream().use { assertTrue(image.compress(Bitmap.CompressFormat.JPEG, 95, it)) }
            image.recycle()
            val item = (repo.finalizeCapture(capture.evidenceId, true, 320, 240) as FinalizeResult.Ready).evidence
            val hash = StreamingHasher.sha256Hex(repo.resolveFile(item))
            db.assistanceDao().put(AssistanceRecord(item.id, a.id, "T1", 1, "test-generation", item.relativePath,
                hash, null, "QUEUED", "queued", null, null, null))
            AssistanceRunner(db, files, OnDeviceAssistance(context)).run(item.id, "test-generation")
            assertEquals(hash, StreamingHasher.sha256Hex(repo.resolveFile(item)))
            assertTrue(db.assistanceDao().get(item.id)!!.resultJson!!.contains("DARK"))
            db.close()
            db = AppDatabase.build(context, name)
            assertEquals("COMPLETED", db.assistanceDao().get(item.id)?.status)
            val vault = VaultKeysetProvider(context)
            fun orchestrator(coordinator: EvidenceAssistanceCoordinator? = null) = SealOrchestrator(
                db.assessmentDraftDao(), db.evidenceDraftDao(), db.outboxDao(), files, rules,
                PhotoOptimizer(), VideoOptimizer(context), vault, "p8-instrumentation", "p8-test-${System.nanoTime()}", coordinator)
            assertEquals(ProcessOutcome.AllFit, orchestrator().processEvidence(a.id))
            val sealing = orchestrator(EvidenceAssistanceCoordinator(context, db, files))
            sealing.setAttestation(a.id, true)
            assertEquals(SealOutcome.Sealed, sealing.seal(a.id)) // warnings cannot gate sealing
            val sealed = db.assessmentDraftDao().getById(a.id)!!
            val plain = File(context.cacheDir, "p8-manifest-${System.nanoTime()}.json")
            try {
                vault.getOrCreateCipher().decryptFile(files.resolveRelativePath(sealed.manifestVaultRelativePath!!), plain,
                    VaultStreamCipher.associatedData(a.id, sealed.revisionId!!, "manifest", "manifest"))
                val envelope = SignedManifestPackage.fromJsonBytes(plain.readBytes())
                val bytes = Base64.decode(envelope.manifestBase64, Base64.NO_WRAP)
                val manifest = SealManifest.CANONICAL_JSON.decodeFromString<SealManifest>(bytes.decodeToString())
                assertEquals(2, manifest.schemaVersion)
                val entry = manifest.evidence.single()
                assertEquals(hash, entry.sha256)
                assertEquals(sealed.revisionId, entry.assistance!!.revisionId)
                assertTrue(entry.assistance!!.flags.any { it.type == AssistanceFlagType.DARK })
            } finally { plain.delete() }
        } finally {
            // Scoped cleanup ONLY of this test's own assessment tree and database.
            files.deleteAssessmentTree(a.id); files.deleteP5TempTree(a.id); files.deleteVaultTree(a.id)
            db.close(); context.deleteDatabase(name)
        }
    }
}
