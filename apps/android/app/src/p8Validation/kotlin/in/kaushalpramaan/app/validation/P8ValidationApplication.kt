package `in`.kaushalpramaan.app.validation

import android.app.Application
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Process
import android.os.SystemClock
import android.provider.Settings
import androidx.work.WorkManager
import `in`.kaushalpramaan.app.data.assistance.EvidenceAssistanceCoordinator
import `in`.kaushalpramaan.app.data.draft.AppDatabase
import `in`.kaushalpramaan.app.data.sync.SyncWorker
import java.io.File
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.core.Delegate
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.handlandmarker.HandLandmarker

/** Opt-in QA UID only. A read-only observer lets the host inspect durable state
 * across an actual OS process stop/relaunch without restarting instrumentation
 * on each poll. Never writes Room, enqueues work, records media, or logs secrets.
 * Its polling overhead means this build is unsuitable for inference benchmarks. */
class P8ValidationApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        check(packageName == "in.kaushalpramaan.app.p8validation")
        CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
            val db = AppDatabase.getInstance(this@P8ValidationApplication)
            while (isActive) {
                val state = runCatching { snapshot(db) }.getOrElse {
                    JSONObject().put("error", it.javaClass.simpleName)
                }
                val temp = File(filesDir, "p8-validation-state.tmp")
                temp.writeText(state.toString())
                check(temp.renameTo(File(filesDir, "p8-validation-state.json")))
                // Explicit private QA signal, only after all real workers have
                // finished. Diagnose model initialisation without decoding media
                // or changing production evidence/results/scheduling.
                val probe = File(filesDir, "p8-native-probe.request")
                val rows = state.optJSONArray("evidence")
                val idle = rows != null && (0 until rows.length()).all {
                    rows.getJSONObject(it).optString("status") !in setOf("QUEUED", "RUNNING")
                }
                if (probe.exists() && idle) {
                    probe.delete()
                    File(filesDir, "p8-native-probe.txt").writeText(nativeProbe())
                }
                delay(250)
            }
        }
    }

    private fun nativeProbe(): String = try {
        val config = JSONObject(assets.open("hands/model.json").bufferedReader().use { it.readText() })
        HandLandmarker.createFromOptions(this, HandLandmarker.HandLandmarkerOptions.builder()
            .setBaseOptions(BaseOptions.builder().setModelAssetPath(config.getString("asset")).setDelegate(Delegate.CPU).build())
            .setRunningMode(RunningMode.VIDEO).setNumHands(config.getInt("num_hands"))
            .setMinHandDetectionConfidence(config.getDouble("min_detection_confidence").toFloat())
            .setMinHandPresenceConfidence(config.getDouble("min_presence_confidence").toFloat())
            .setMinTrackingConfidence(config.getDouble("min_tracking_confidence").toFloat()).build()).use { "MODEL_INITIALISED" }
    } catch (error: Throwable) { error.stackTraceToString() }

    private suspend fun snapshot(db: AppDatabase): JSONObject {
        val cm = getSystemService(ConnectivityManager::class.java)
        val network = cm.getNetworkCapabilities(cm.activeNetwork)
        val root = JSONObject().put("package", packageName).put("pid", Process.myPid())
            .put("elapsedRealtimeMs", SystemClock.elapsedRealtime())
            .put("airplaneMode", Settings.Global.getInt(contentResolver, Settings.Global.AIRPLANE_MODE_ON, 0))
            .put("validatedInternet", network?.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) == true)
            .put("internetNetworkCount", cm.allNetworks.count {
                cm.getNetworkCapabilities(it)?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true
            })
        val assessment = db.assessmentDraftDao().getActiveOnce() ?: return root
        root.put("assessmentId", assessment.id).put("revisionNumber", assessment.currentRevisionNumber)
            .put("sealState", assessment.sealState.name).put("synced", assessment.syncedAtMillis != null)
            .put("serverAssessmentId", assessment.serverAssessmentId ?: JSONObject.NULL)
        val wm = WorkManager.getInstance(this)
        val evidence = JSONArray()
        for (item in db.evidenceDraftDao().getAllForAssessmentOnce(assessment.id)) {
            val row = JSONObject().put("id", item.id).put("taskId", item.taskId).put("kind", item.kind.name)
                .put("state", item.state.name).put("finalState", item.finalState.name)
                .put("bytes", item.finalBytes ?: item.byteSize)
                .put("durationMs", item.finalDurationMillis ?: item.durationMillis ?: JSONObject.NULL)
                .put("historical", item.fromPreviousRevision)
            db.assistanceDao().get(item.id)?.let { a ->
                row.put("generation", a.generation).put("status", a.status).put("stage", a.stage)
                    .put("sha256", a.inputSha256).put("revisionNumber", a.revisionNumber)
                    .put("result", a.resultJson?.let(::JSONObject) ?: JSONObject.NULL)
                    .put("sealedSnapshot", a.sealedSnapshotJson?.let(::JSONObject) ?: JSONObject.NULL)
            }
            row.put("work", JSONArray().apply {
                wm.getWorkInfosForUniqueWork(EvidenceAssistanceCoordinator.tag(item.id)).get().forEach {
                    put(JSONObject().put("id", it.id).put("state", it.state.name)
                        .put("attempt", it.runAttemptCount).put("network", it.constraints.requiredNetworkType.name))
                }
            })
            evidence.put(row)
        }
        root.put("evidence", evidence)
        root.put("syncWork", JSONArray().apply {
            assessment.revisionId?.let { revision ->
                wm.getWorkInfosForUniqueWork(SyncWorker.uniqueWorkName(assessment.id, revision)).get().forEach {
                    put(JSONObject().put("id", it.id).put("state", it.state.name)
                        .put("attempt", it.runAttemptCount).put("network", it.constraints.requiredNetworkType.name))
                }
            }
        })
        root.put("outbox", JSONArray().apply {
            db.outboxDao().getAllForAssessmentOnce(assessment.id).forEach {
                put(JSONObject().put("kind", it.kind.name).put("state", it.syncState.name)
                    .put("uploadedBytes", it.bytesUploaded).put("error", it.lastErrorCategory ?: JSONObject.NULL))
            }
        })
        return root
    }
}
