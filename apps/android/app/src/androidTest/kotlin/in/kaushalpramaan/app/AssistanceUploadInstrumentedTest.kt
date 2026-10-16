package `in`.kaushalpramaan.app

import android.graphics.Bitmap
import android.graphics.Color
import android.os.Bundle
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.data.assistance.*
import `in`.kaushalpramaan.app.data.draft.*
import `in`.kaushalpramaan.app.data.seal.*
import `in`.kaushalpramaan.app.data.sync.*
import `in`.kaushalpramaan.core.mapping.RulesLoader
import `in`.kaushalpramaan.core.seal.*
import `in`.kaushalpramaan.media.*
import java.net.URI
import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Real Android inference/signing/sync -> isolated local PostgreSQL API -> P7 recapture.
 * Run only with infra/docker-compose.p8-test.yml and adb reverse tcp:18008 tcp:18008.
 * Inputs are synthetic. This does not measure CameraX/Compose or field accuracy. */
@RunWith(AndroidJUnit4::class)
class AssistanceUploadInstrumentedTest {
    @Test fun native_flags_survive_real_upload_and_targeted_reassessment() = runBlocking {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val base = InstrumentationRegistry.getArguments().getString("p8ApiBaseUrl") ?: "http://127.0.0.1:18008"
        require(URI(base).host in setOf("127.0.0.1", "localhost") && URI(base).port == 18008) {
            "This fixture may only target the isolated local P8 stack on port 18008"
        }
        val runId = "p8-native-${System.nanoTime()}"
        val name = "$runId.db"
        val db = AppDatabase.build(context, name)
        val files = EvidenceFileManager(context)
        val rules = RulesLoader.load()
        val repo = EvidenceRepository(db.assessmentDraftDao(), db.taskDraftDao(), db.evidenceDraftDao(), files, rules)
        val coordinator = EvidenceAssistanceCoordinator(context, db, files)
        val vault = VaultKeysetProvider(context)
        val signingAlias = "$runId-key"
        fun sealing(withAssistance: Boolean) = SealOrchestrator(db.assessmentDraftDao(), db.evidenceDraftDao(), db.outboxDao(), files,
            rules, PhotoOptimizer(), VideoOptimizer(context), vault, "p8-native", signingAlias, if (withAssistance) coordinator else null)
        val endpoint = object : SyncEndpointConfig {
            override fun baseUrl() = base
            override fun supportsRuntimeOverride() = true
            override fun setOverrideBaseUrl(url: String?) {}
        }
        val sync = SyncRepository(db.assessmentDraftDao(), db.evidenceDraftDao(), db.outboxDao(), files, vault, endpoint)
        val http = OkHttpClient()
        fun api(method: String, path: String, token: String? = null, body: JSONObject? = null, expected: Int = 200): String {
            val builder = Request.Builder().url(base + path)
            if (token != null) builder.header("Authorization", "Bearer $token")
            builder.method(method, if (method == "GET") null else (body?.toString() ?: "{}").toRequestBody("application/json".toMediaType()))
            return http.newCall(builder.build()).execute().use {
                assertEquals("Local test API $method $path", expected, it.code)
                it.body!!.string()
            }
        }
        val assessment = repo.createOrResumeAssessment(runId, "en", null)
        val timings = JSONObject()
        try {
            val photo = repo.beginCapture(assessment.id, "T1", EvidenceType.PHOTO, false) as BeginCaptureResult.Started
            Bitmap.createBitmap(320, 240, Bitmap.Config.ARGB_8888).apply {
                eraseColor(Color.BLACK)
                photo.stagingFile.outputStream().use { assertTrue(compress(Bitmap.CompressFormat.JPEG, 95, it)) }
                recycle()
            }
            assertTrue(repo.finalizeCapture(photo.evidenceId, true, 320, 240) is FinalizeResult.Ready)
            suspend fun video(asset: String): String {
                val begin = repo.beginCapture(assessment.id, "T2", EvidenceType.VIDEO, false) as BeginCaptureResult.Started
                instrumentation.context.assets.open("fixtures/$asset").use { input -> begin.stagingFile.outputStream().use { input.copyTo(it) } }
                val metadata = VideoOptimizer(context).validateContainer(begin.stagingFile)!!
                assertTrue(repo.finalizeCapture(begin.evidenceId, true, metadata.widthPx, metadata.heightPx, metadata.durationMs) is FinalizeResult.Ready)
                return begin.evidenceId
            }
            val oldVideo = video("synthetic-rotation90.mp4")
            suspend fun processAndAnalyse(vararg ids: String) {
                assertEquals(ProcessOutcome.AllFit, sealing(false).processEvidence(assessment.id))
                for (id in ids) {
                    val item = db.evidenceDraftDao().getById(id)!!
                    val path = EvidenceAssistanceCoordinator.inputPath(item)
                    val generation = "$runId-$id"
                    db.assistanceDao().put(AssistanceRecord(id, assessment.id, item.taskId,
                        db.assessmentDraftDao().getById(assessment.id)!!.currentRevisionNumber, generation, path,
                        StreamingHasher.sha256Hex(files.resolveRelativePath(path)), EvidenceAssistanceCoordinator.duration(item),
                        "QUEUED", "queued", null, null, null))
                    val start = SystemClock.elapsedRealtime()
                    AssistanceRunner(db, files, OnDeviceAssistance(context)).run(id, generation)
                    timings.put(id, SystemClock.elapsedRealtime() - start)
                    assertTrue(db.assistanceDao().get(id)!!.status in setOf("COMPLETED", "PARTIAL"))
                }
            }
            processAndAnalyse(photo.evidenceId, oldVideo)
            assertTrue(db.assistanceDao().get(photo.evidenceId)!!.resultJson!!.contains("DARK"))
            sealing(true).setAttestation(assessment.id, true)
            assertEquals(SealOutcome.Sealed, sealing(true).seal(assessment.id))
            val frozenPhoto = db.assistanceDao().get(photo.evidenceId)!!.sealedSnapshotJson!!
            val frozenVideo = db.assistanceDao().get(oldVideo)!!.sealedSnapshotJson!!
            assertEquals(SyncRunOutcome.Success, sync.syncAssessment(assessment.id))
            val aid = db.assessmentDraftDao().getById(assessment.id)!!.serverAssessmentId!!
            assertTrue(db.outboxDao().getAllForAssessmentOnce(assessment.id).isEmpty())
            val login = JSONObject(api("POST", "/auth/login", body = JSONObject()
                .put("email", "p8-assessor@parakh.test").put("password", "p8-isolated-test-only")))
            val token = login.getString("access_token")
            fun detail() = JSONObject(api("GET", "/assessments/$aid", token))
            fun assertSnapshot(expected: String, actual: JSONObject) = assertEquals(
                EvidenceAssistanceCoordinator.JSON.decodeFromString<AssistanceSnapshot>(expected),
                EvidenceAssistanceCoordinator.JSON.decodeFromString<AssistanceSnapshot>(actual.toString()))
            fun evidence(detail: JSONObject, task: String): List<JSONObject> {
                val tasks = detail.getJSONArray("tasks")
                val array = (0 until tasks.length()).map { tasks.getJSONObject(it) }.single { it.getString("task_code") == task }.getJSONArray("evidence")
                return (0 until array.length()).map { array.getJSONObject(it) }
            }
            val first = detail()
            assertEquals("submitted", first.getString("status"))
            assertSnapshot(frozenPhoto, evidence(first, "T1").single().getJSONObject("assistance"))
            assertSnapshot(frozenVideo, evidence(first, "T2").single().getJSONObject("assistance"))
            val reviews = JSONArray(api("GET", "/assessments/$aid/review", token))
            assertTrue((0 until reviews.length()).all { reviews.getJSONObject(it).isNull("score") })
            api("POST", "/assessments/$aid/start-review", token)
            api("POST", "/assessments/$aid/reassessment-requests", token, JSONObject().put("task_codes", JSONArray().put("T2"))
                .put("reason", "P8 synthetic native revision test").put("capture_instructions", "Recapture T2 only"), 201)
            assertTrue(WorkerUpdatesRepository(db.assessmentDraftDao(), db.taskDraftDao(), endpoint).pollAndApply(assessment.id) is WorkerUpdatesPollResult.Applied)
            assertTrue(db.taskDraftDao().getAllOnce(assessment.id).single { it.taskId == "T1" }.locked)
            assertFalse(db.taskDraftDao().getAllOnce(assessment.id).single { it.taskId == "T2" }.locked)
            val newVideo = video("synthetic-landscape.mp4")
            processAndAnalyse(newVideo)
            sealing(true).setAttestation(assessment.id, true)
            assertEquals(SealOutcome.Sealed, sealing(true).sealTargetedRevision(assessment.id, setOf("T2")))
            assertEquals(SyncRunOutcome.Success, sync.syncAssessment(assessment.id))
            val final = detail()
            assertEquals(2, final.getInt("revision_number"))
            val videos = evidence(final, "T2")
            assertEquals(2, videos.size)
            val historical = videos.single { !it.getBoolean("is_current_revision") }
            val current = videos.single { it.getBoolean("is_current_revision") }
            assertSnapshot(frozenVideo, historical.getJSONObject("assistance"))
            assertEquals(2, current.getJSONObject("assistance").getInt("revisionNumber"))
            assertSnapshot(frozenPhoto, evidence(final, "T1").single().getJSONObject("assistance"))
            val result = JSONObject().put("runId", runId).put("assessmentId", aid)
                .put("historicalVideoEvidenceId", historical.getLong("id")).put("currentVideoEvidenceId", current.getLong("id"))
                .put("photoEvidenceId", evidence(final, "T1").single().getLong("id"))
                .put("analysisWallMsByEvidence", timings).put("verdict", "PASS")
                .put("source", JSONObject(context.assets.open("assistance-source.json").bufferedReader().use { it.readText() }))
            instrumentation.sendStatus(2, Bundle().apply { putString("p8NativeResult", result.toString()) })
        } finally {
            files.deleteAssessmentTree(assessment.id); files.deleteP5TempTree(assessment.id); files.deleteVaultTree(assessment.id)
            db.close(); context.deleteDatabase(name)
        }
    }
}
