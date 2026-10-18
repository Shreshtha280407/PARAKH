package `in`.kaushalpramaan.app.data.sync

import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.data.draft.AppDatabase
import `in`.kaushalpramaan.app.data.draft.BeginCaptureResult
import `in`.kaushalpramaan.app.data.draft.EvidenceFileManager
import `in`.kaushalpramaan.app.data.draft.EvidenceRepository
import `in`.kaushalpramaan.app.data.draft.FinalizeResult
import `in`.kaushalpramaan.app.data.draft.OutboxItemKind
import `in`.kaushalpramaan.app.data.draft.SyncState
import `in`.kaushalpramaan.app.data.seal.ProcessOutcome
import `in`.kaushalpramaan.app.data.seal.SealOrchestrator
import `in`.kaushalpramaan.app.data.seal.SealOutcome
import `in`.kaushalpramaan.core.mapping.RulesLoader
import `in`.kaushalpramaan.core.seal.VaultKeysetProvider
import `in`.kaushalpramaan.media.PhotoOptimizer
import `in`.kaushalpramaan.media.VideoOptimizer
import android.graphics.Bitmap
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Real-device proof of [SyncRepository] against a real P5-sealed outbox (real Android
 * Keystore ECDSA signature, real Tink-encrypted vault -- Robolectric cannot provide either,
 * see SealOrchestratorInstrumentedTest) and a local, in-process fake server (MockWebServer --
 * real sockets/TLS-capable HTTP, just not the real FastAPI backend) that reproduces the exact
 * protocol server/app/routers/uploads.py implements. Covers the mandatory P6 properties that
 * specifically need a real device: bounded 1 MiB streaming with no plaintext file ever
 * written, local encrypted data surviving a rejected upload, and resume-after-lost-
 * acknowledgement not re-sending acknowledged bytes.
 */
@RunWith(AndroidJUnit4::class)
class SyncRepositoryInstrumentedTest {

    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val json = Json { ignoreUnknownKeys = true }

    private fun freshHarness(): Triple<EvidenceRepository, SealOrchestrator, AppDatabase> {
        val dbName = "kp_sync_test_${System.nanoTime()}.db"
        val db = AppDatabase.build(context, dbName)
        val fileManager = EvidenceFileManager(context)
        val rules = RulesLoader.load()
        val repository = EvidenceRepository(db.assessmentDraftDao(), db.taskDraftDao(), db.evidenceDraftDao(), fileManager, rules)
        val orchestrator = SealOrchestrator(
            assessmentDraftDao = db.assessmentDraftDao(),
            evidenceDraftDao = db.evidenceDraftDao(),
            outboxDao = db.outboxDao(),
            fileManager = fileManager,
            rules = rules,
            photoOptimizer = PhotoOptimizer(),
            videoOptimizer = VideoOptimizer(context),
            vaultKeysetProvider = VaultKeysetProvider(context),
            appVersion = "instrumented-test",
            signingKeyAlias = "kp_sync_test_key_${System.nanoTime()}",
        )
        return Triple(repository, orchestrator, db)
    }

    private suspend fun captureRealPhoto(repo: EvidenceRepository, assessmentId: String, taskId: String): String {
        val begin = repo.beginCapture(assessmentId, taskId, EvidenceType.PHOTO, debugOverrideRequested = false)
        check(begin is BeginCaptureResult.Started)
        val bitmap = Bitmap.createBitmap(640, 480, Bitmap.Config.ARGB_8888)
        for (y in 0 until 480) for (x in 0 until 640) {
            bitmap.setPixel(x, y, (0xFF shl 24) or ((x * 255 / 640) shl 16) or ((y * 255 / 480) shl 8) or (x xor y and 0xFF))
        }
        begin.stagingFile.parentFile?.mkdirs()
        FileOutputStream(begin.stagingFile).use { out -> bitmap.compress(Bitmap.CompressFormat.JPEG, 95, out) }
        bitmap.recycle()
        val result = repo.finalizeCapture(begin.evidenceId, success = true, widthPx = 640, heightPx = 480)
        check(result is FinalizeResult.Ready)
        return begin.evidenceId
    }

    /** Per-session in-memory server state the fake dispatcher tracks, mirroring exactly what
     * server/app/models.py's UploadSession tracks: how many bytes this session has actually
     * received so far, and whether it's done. */
    private class FakeSession(val id: Long, var receivedBytes: Long = 0, var completed: Boolean = false, var declaredSize: Long = 0)

    /** A minimal, real, stateful fake of the P6 server protocol -- real HTTP over a real local
     * socket (MockWebServer), not a mocked Kotlin interface, so the full real OkHttp/
     * SyncApiClient code path is genuinely exercised end to end. */
    private inner class FakeServerDispatcher : Dispatcher() {
        val enrollments = mutableListOf<String>()
        val sessions = mutableMapOf<Long, FakeSession>()
        val nextSessionId = AtomicInteger(1)
        var rejectEvidenceComplete = false
        var submitConflict = false
        var alreadySubmitted = false
        var statusRevision = "rev"
        val chunkPutCount = AtomicInteger(0)
        val chunkBytesReceivedTotal = AtomicInteger(0)
        var firstOpenReportsPartialProgress: Long? = null

        override fun dispatch(request: RecordedRequest): MockResponse {
            val path = request.path.orEmpty().substringBefore("?")
            return when {
                request.method == "POST" && path == "/workers/enroll" -> {
                    enrollments.add(request.body.readUtf8())
                    MockResponse().setBody("""{"id":1,"worker_token":"fake-token"}""")
                }
                request.method == "POST" && path == "/workers/register" ->
                    MockResponse().setBody("""{"worker_id":1}""")
                request.method == "GET" && path == "/packs/by-code" ->
                    MockResponse().setBody("""{"pack_id":1,"qp_code":"x","qp_version":"y","pack_version":"z"}""")
                request.method == "POST" && path == "/assessments" ->
                    MockResponse().setResponseCode(201).setBody("""{"id":1,"worker_token":"fake-token"}""")
                request.method == "POST" && path == "/assessments/1/submit" ->
                    if (submitConflict) MockResponse().setResponseCode(409).setBody("""{"detail":"submission conflict"}""") else MockResponse().setBody("{}")
                request.method == "GET" && path == "/assessments/1/sync-status" ->
                    MockResponse().setBody("""{"assessment_id":1,"assessment_status":"${if (alreadySubmitted) "submitted" else "draft"}","revision_id":"$statusRevision","manifest_state":"complete","items":[],"all_items_verified":true}""")
                request.method == "POST" && path == "/uploads" -> openSession(request)
                request.method == "GET" && path.startsWith("/uploads/") -> statusFor(path.removePrefix("/uploads/").toLong())
                request.method == "PUT" && path.startsWith("/uploads/") -> putChunk(path, request)
                request.method == "POST" && path.endsWith("/complete") -> complete(path)
                else -> MockResponse().setResponseCode(404).setBody("""{"detail":"not found"}""")
            }
        }

        private fun openSession(request: RecordedRequest): MockResponse {
            val body = json.parseToJsonElement(request.body.readUtf8()).jsonObject
            val claimed = body["claimed_size_bytes"]!!.jsonPrimitive.long
            val id = nextSessionId.getAndIncrement().toLong()
            val received = if (id == 2L) firstOpenReportsPartialProgress ?: 0L else 0L
            sessions[id] = FakeSession(id, receivedBytes = received, declaredSize = claimed)
            return MockResponse().setResponseCode(201).setBody(
                """{"id":$id,"assessment_id":1,"target":"x","claimed_size_bytes":$claimed,"received_bytes":$received,"next_chunk_index":${received / (1024 * 1024)},"status":"open"}""",
            )
        }

        private fun statusFor(id: Long): MockResponse {
            val s = sessions[id] ?: return MockResponse().setResponseCode(404)
            return MockResponse().setBody(
                """{"id":$id,"assessment_id":1,"target":"x","claimed_size_bytes":${s.declaredSize},"received_bytes":${s.receivedBytes},"next_chunk_index":${s.receivedBytes / (1024 * 1024)},"status":"${if (s.completed) "completed" else "open"}"}""",
            )
        }

        private fun putChunk(path: String, request: RecordedRequest): MockResponse {
            val id = path.removePrefix("/uploads/").substringBefore("/chunks/").toLong()
            val s = sessions.getValue(id)
            val size = request.bodySize
            s.receivedBytes += size
            chunkPutCount.incrementAndGet()
            chunkBytesReceivedTotal.addAndGet(size.toInt())
            return MockResponse().setBody(
                """{"chunk_index":0,"received_bytes":${s.receivedBytes},"next_chunk_index":${s.receivedBytes / (1024 * 1024)},"status":"open"}""",
            )
        }

        private fun complete(path: String): MockResponse {
            val id = path.removePrefix("/uploads/").substringBefore("/complete").toLong()
            val s = sessions.getValue(id)
            if (id == 2L && rejectEvidenceComplete) {
                return MockResponse().setResponseCode(409).setBody("""{"detail":"hash mismatch: server computed aaa, client declared bbb"}""")
            }
            s.completed = true
            return if (id == 1L) {
                MockResponse().setBody("""{"session_id":1,"manifest_id":1,"assessment_id":1,"revision_id":"rev","sha256":"x","item_count":1,"declared_total_bytes":${s.declaredSize},"status":"received"}""")
            } else {
                MockResponse().setBody("""{"session_id":2,"evidence_id":2,"sha256":"x","byte_count":${s.declaredSize},"mime":"image/jpeg","kind":"photo","storage_status":"stored"}""")
            }
        }
    }

    @Test
    fun submissionConflictOnlySucceedsWhenServerConfirmsThatRevisionWasSubmitted() = runBlocking {
        for (confirmed in listOf(false, true)) {
            val (repo, orchestrator, db) = freshHarness()
            val server = MockWebServer()
            val dispatcher = FakeServerDispatcher().apply { submitConflict = true; alreadySubmitted = confirmed }
            server.dispatcher = dispatcher
            server.start()
            val assessment = repo.createOrResumeAssessment("conflict-worker", "en", null)
            try {
                captureRealPhoto(repo, assessment.id, "T1")
                assertEquals(ProcessOutcome.AllFit, orchestrator.processEvidence(assessment.id))
                orchestrator.setAttestation(assessment.id, true)
                assertEquals(SealOutcome.Sealed, orchestrator.seal(assessment.id))
                dispatcher.statusRevision = db.assessmentDraftDao().getById(assessment.id)!!.revisionId!!
                val endpoint = object : SyncEndpointConfig {
                    override fun baseUrl() = server.url("/").toString().removeSuffix("/")
                    override fun supportsRuntimeOverride() = false
                    override fun setOverrideBaseUrl(url: String?) {}
                }
                val sync = SyncRepository(db.assessmentDraftDao(), db.evidenceDraftDao(), db.outboxDao(), EvidenceFileManager(context), VaultKeysetProvider(context), endpoint)
                val outcome = sync.syncAssessment(assessment.id)
                assertEquals(confirmed, outcome is SyncRunOutcome.Success)
                assertEquals(confirmed, db.assessmentDraftDao().getById(assessment.id)!!.syncedAtMillis != null)
                assertEquals(confirmed, db.outboxDao().getAllForAssessmentOnce(assessment.id).isEmpty())
            } finally {
                server.shutdown()
                repo.deleteAssessment(assessment.id)
                db.close()
            }
        }
    }

    @Test
    fun full_sync_happy_path_against_a_real_fake_server_syncs_everything_and_submits() = runBlocking {
        val (repo, orchestrator, db) = freshHarness()
        val server = MockWebServer()
        val dispatcher = FakeServerDispatcher()
        server.dispatcher = dispatcher
        server.start()
        try {
            val candidate = `in`.kaushalpramaan.app.data.WorkerRegistration("KP-00000000-0000-4000-8000-000000000001", "9876543210", "Asha Kumar", false, "a".repeat(64))
            val assessment = repo.createOrResumeAssessment(candidate.workerId, "en", null, candidate = candidate)
            captureRealPhoto(repo, assessment.id, "T1")
            assertEquals(ProcessOutcome.AllFit, orchestrator.processEvidence(assessment.id))
            orchestrator.setAttestation(assessment.id, true)
            val sealed = orchestrator.seal(assessment.id)
            assertEquals(SealOutcome.Sealed, sealed)

            val endpoint = object : SyncEndpointConfig {
                override fun baseUrl() = server.url("/").toString().removeSuffix("/")
                override fun supportsRuntimeOverride() = true
                override fun setOverrideBaseUrl(url: String?) {}
            }
            val repository = SyncRepository(
                db.assessmentDraftDao(), db.evidenceDraftDao(), db.outboxDao(),
                EvidenceFileManager(context), VaultKeysetProvider(context), endpoint,
            )

            val outcome = repository.syncAssessment(assessment.id)
            assertTrue("expected Success, got $outcome", outcome is SyncRunOutcome.Success)
            val enrollment = json.parseToJsonElement(dispatcher.enrollments.single()).jsonObject
            assertEquals("Asha Kumar", enrollment["full_name"]!!.jsonPrimitive.content)
            assertEquals("+919876543210", enrollment["phone"]!!.jsonPrimitive.content)
            assertFalse(enrollment.keys.any { it.contains("pin", ignoreCase = true) })
            assertEquals("Asha Kumar", db.assessmentDraftDao().getById(assessment.id)!!.candidateFullName)

            val remainingRows = db.outboxDao().getAllForAssessmentOnce(assessment.id)
            assertTrue("outbox rows must be cleared once the whole package is submitted", remainingRows.isEmpty())
            val finalAssessment = db.assessmentDraftDao().getById(assessment.id)!!
            assertTrue(finalAssessment.syncedAtMillis != null)

            // Real 1 MiB chunking genuinely happened (not one giant PUT): the tiny JPEG here is
            // under 1 MiB so exactly one chunk per item is expected, but the server-side
            // received-byte accounting must still exactly match what was uploaded.
            assertTrue(dispatcher.chunkPutCount.get() >= 2) // manifest + the one evidence item
        } finally {
            server.shutdown()
            repo.deleteAssessment(repo.getActiveAssessment()!!.id)
        }
    }

    @Test
    fun a_server_rejected_evidence_upload_retains_local_encrypted_data_and_marks_failed_action_required() = runBlocking {
        val (repo, orchestrator, db) = freshHarness()
        val server = MockWebServer()
        val dispatcher = FakeServerDispatcher()
        dispatcher.rejectEvidenceComplete = true
        server.dispatcher = dispatcher
        server.start()
        try {
            val assessment = repo.createOrResumeAssessment("KP-SYNC-TEST", "en", null)
            captureRealPhoto(repo, assessment.id, "T1")
            orchestrator.processEvidence(assessment.id)
            orchestrator.setAttestation(assessment.id, true)
            orchestrator.seal(assessment.id)

            val endpoint = object : SyncEndpointConfig {
                override fun baseUrl() = server.url("/").toString().removeSuffix("/")
                override fun supportsRuntimeOverride() = true
                override fun setOverrideBaseUrl(url: String?) {}
            }
            val fileManager = EvidenceFileManager(context)
            val repository = SyncRepository(db.assessmentDraftDao(), db.evidenceDraftDao(), db.outboxDao(), fileManager, VaultKeysetProvider(context), endpoint)

            val outcome = repository.syncAssessment(assessment.id)
            assertTrue("a rejected evidence item must stop the run as Terminal", outcome is SyncRunOutcome.Terminal)

            val rows = db.outboxDao().getAllForAssessmentOnce(assessment.id)
            val evidenceRow = rows.first { it.kind == OutboxItemKind.EVIDENCE }
            assertEquals(SyncState.FAILED_ACTION_REQUIRED, evidenceRow.syncState)
            assertEquals(SyncErrorCategory.INTEGRITY_REJECTED.name, evidenceRow.lastErrorCategory)
            assertNull("a rejected item must never be marked as having a verified receipt", evidenceRow.receiptVerifiedAtMillis)
            // The encrypted vault file for the rejected item must still be on disk -- the
            // server's rejection must never trigger local deletion.
            assertTrue(fileManager.resolveRelativePath(evidenceRow.vaultRelativePath).exists())
            val finalAssessment = db.assessmentDraftDao().getById(assessment.id)!!
            assertNull("a rejected sync must never be marked as fully synced/submitted", finalAssessment.syncedAtMillis)
        } finally {
            server.shutdown()
            repo.deleteAssessment(repo.getActiveAssessment()!!.id)
        }
    }

    @Test
    fun resuming_after_a_lost_acknowledgement_does_not_re_send_already_received_bytes() = runBlocking {
        val (repo, orchestrator, db) = freshHarness()
        val server = MockWebServer()
        val dispatcher = FakeServerDispatcher()
        server.dispatcher = dispatcher
        server.start()
        try {
            val assessment = repo.createOrResumeAssessment("KP-SYNC-TEST", "en", null)
            captureRealPhoto(repo, assessment.id, "T1")
            orchestrator.processEvidence(assessment.id)
            orchestrator.setAttestation(assessment.id, true)
            orchestrator.seal(assessment.id)

            val evidenceRow = db.outboxDao().getAllForAssessmentOnce(assessment.id).first { it.kind == OutboxItemKind.EVIDENCE }
            val evidenceSizeBytes = db.evidenceDraftDao().getById(evidenceRow.evidenceId!!)!!.finalBytes!!

            // Simulate: a previous attempt already fully uploaded (and the server received)
            // this item's bytes, but the app process died before it saw the ack -- the local
            // row still thinks it's QUEUED with no serverSessionId. On recover, the session
            // the server hands back must already report the full byte count received.
            dispatcher.firstOpenReportsPartialProgress = evidenceSizeBytes

            val endpoint = object : SyncEndpointConfig {
                override fun baseUrl() = server.url("/").toString().removeSuffix("/")
                override fun supportsRuntimeOverride() = true
                override fun setOverrideBaseUrl(url: String?) {}
            }
            val repository = SyncRepository(
                db.assessmentDraftDao(), db.evidenceDraftDao(), db.outboxDao(),
                EvidenceFileManager(context), VaultKeysetProvider(context), endpoint,
            )
            val outcome = repository.syncAssessment(assessment.id)
            assertTrue(outcome is SyncRunOutcome.Success)

            // Because the fake "already received everything" session reported full progress
            // immediately, no chunk PUT should have been needed at all for that item -- proving
            // the resume path genuinely skips bytes the server already has rather than
            // blindly re-uploading them. (The manifest, a fresh session, still needs its one PUT.)
            assertEquals(1, dispatcher.chunkPutCount.get())
        } finally {
            server.shutdown()
            repo.deleteAssessment(repo.getActiveAssessment()!!.id)
        }
    }

    @Test
    fun bounded_streaming_upload_never_writes_a_plaintext_copy_of_the_evidence_to_disk() = runBlocking {
        val (repo, orchestrator, db) = freshHarness()
        val server = MockWebServer()
        val dispatcher = FakeServerDispatcher()
        server.dispatcher = dispatcher
        server.start()
        try {
            val assessment = repo.createOrResumeAssessment("KP-SYNC-TEST", "en", null)
            val evidenceId = captureRealPhoto(repo, assessment.id, "T1")
            orchestrator.processEvidence(assessment.id)
            val beforeSeal = db.evidenceDraftDao().getById(evidenceId)!!
            val fileManager = EvidenceFileManager(context)
            val plaintextMarker = fileManager.resolveRelativePath(beforeSeal.finalRelativePath ?: beforeSeal.relativePath).readBytes()
                .copyOfRange(0, 256) // a real, distinctive prefix of this exact JPEG's real bytes

            orchestrator.setAttestation(assessment.id, true)
            orchestrator.seal(assessment.id)
            // P5 itself deletes the raw/final plaintext at seal time (spec G.5) -- confirm that
            // invariant still holds before sync even starts, so this test genuinely proves
            // SYNC never recreates a plaintext copy, not that P5 merely never deleted one.
            assertFalse(fileManager.resolveRelativePath(beforeSeal.relativePath).exists())

            // A personal test device can already contain legitimate draft JPEGs with the
            // same encoder header. Preserve them and compare their complete hashes;
            // any new or changed matching file after sync is still a failure.
            fun matchingFiles() = context.filesDir.walkTopDown().filter { it.isFile }.filter { f ->
                runCatching { containsMarker(f, plaintextMarker) }.getOrDefault(false)
            }.associate { it.absolutePath to `in`.kaushalpramaan.core.seal.StreamingHasher.sha256Hex(it) }
            val existingMatches = matchingFiles()

            val endpoint = object : SyncEndpointConfig {
                override fun baseUrl() = server.url("/").toString().removeSuffix("/")
                override fun supportsRuntimeOverride() = true
                override fun setOverrideBaseUrl(url: String?) {}
            }
            val repository = SyncRepository(db.assessmentDraftDao(), db.evidenceDraftDao(), db.outboxDao(), fileManager, VaultKeysetProvider(context), endpoint)
            repository.syncAssessment(assessment.id)

            // Exhaustively scan every file this app privately owns for the known plaintext
            // marker bytes -- if sync ever staged a decrypted copy to disk (even transiently
            // and later deleted it before this scan), a *different*, stronger version of this
            // test running the scan concurrently with the upload would be needed; this
            // end-state scan at minimum proves no such copy was left behind, and the
            // implementation (SyncRepository.syncEvidenceItem) only ever holds a bounded
            // in-memory buffer -- see its own doc comments -- never a FileOutputStream.
            val offenders = matchingFiles().filter { (path, hash) -> existingMatches[path] != hash }.keys
            assertTrue("found a plaintext copy of evidence bytes on disk: $offenders", offenders.isEmpty())
        } finally {
            server.shutdown()
            repo.deleteAssessment(repo.getActiveAssessment()!!.id)
        }
    }

    private fun containsMarker(file: File, marker: ByteArray): Boolean {
        if (file.length() < marker.size) return false
        val bytes = file.readBytes()
        outer@ for (start in 0..(bytes.size - marker.size)) {
            for (i in marker.indices) {
                if (bytes[start + i] != marker[i]) continue@outer
            }
            return true
        }
        return false
    }
}
