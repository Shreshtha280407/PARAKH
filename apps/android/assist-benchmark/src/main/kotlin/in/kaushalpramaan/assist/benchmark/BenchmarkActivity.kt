package `in`.kaushalpramaan.assist.benchmark

import android.app.Activity
import android.app.ActivityManager
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Debug
import android.provider.Settings
import android.widget.TextView
import `in`.kaushalpramaan.assist.hands.HandsAnalyzer
import `in`.kaushalpramaan.assist.quality.*
import java.io.File
import java.security.MessageDigest
import kotlinx.coroutines.*
import org.json.JSONObject

/** Isolated offline harness. No production app dependency, networking/storage permissions,
 * accounts, database or Keystore access. ADB stages only explicit test files with run-as.
 */
class BenchmarkActivity : Activity() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var active: Job? = null
    private lateinit var status: TextView
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        status = TextView(this).apply { text = "Isolated assistance harness. Awaiting private test plan."; textSize = 18f }
        setContentView(status)
        process(intent)
    }
    override fun onNewIntent(intent: Intent) { super.onNewIntent(intent); process(intent) }
    private fun process(intent: Intent) {
        when (intent.getStringExtra("action")) {
            "cancel" -> { active?.cancel(); status.text = "Cancellation requested." }
            "run" -> if (active?.isActive != true) {
                val runId = intent.getStringExtra("run_id") ?: "run"
                require(runId.matches(Regex("[A-Za-z0-9_-]{1,64}")))
                active = scope.launch { execute(runId) }
            }
        }
    }
    private suspend fun execute(runId: String) {
        val reports = File(filesDir, "reports").apply { mkdirs() }
        val output = File(reports, "$runId.jsonl")
        val done = File(reports, "$runId.done.json")
        if (output.exists() || done.exists()) { status.text = "Run identifier already exists; use a new one."; return }
        check(output.createNewFile())
        val started = System.nanoTime()
        var peakPssKb = 0; var peakNativeBytes = 0L; var memorySamples = 0
        val memoryJob = scope.launch(Dispatchers.Default) {
            while (isActive) {
                val info = Debug.MemoryInfo(); Debug.getMemoryInfo(info)
                peakPssKb = maxOf(peakPssKb, info.totalPss)
                peakNativeBytes = maxOf(peakNativeBytes, Debug.getNativeHeapAllocatedSize())
                memorySamples++; delay(100)
            }
        }
        var finalStatus = "FAILED"; var failure: String? = null
        try {
            withContext(Dispatchers.Default) {
                val plan = JSONObject(File(filesDir, "plan.json").readText())
                val builtSource = assets.open("assistance-source.json").use { JSONObject(it.readBytes().toString(Charsets.UTF_8)).getString("source_version") }
                require(builtSource == plan.getString("source_version")) { "Installed APK/source plan differ; rebuild and install the isolated harness with -r" }
                val ram = ActivityManager.MemoryInfo()
                (getSystemService(ACTIVITY_SERVICE) as ActivityManager).getMemoryInfo(ram)
                output.appendText(obj("type" to "run", "run_id" to runId, "source_version" to builtSource,
                    "manufacturer" to Build.MANUFACTURER, "model" to Build.MODEL, "device" to Build.DEVICE,
                    "api" to Build.VERSION.SDK_INT, "abis" to Build.SUPPORTED_ABIS.joinToString(), "ram_bytes" to ram.totalMem,
                    "airplane_mode" to Settings.Global.getInt(contentResolver, Settings.Global.AIRPLANE_MODE_ON, 0),
                    "memory_method" to "Debug.getMemoryInfo totalPss and native heap allocated, sampled every ~100ms; observed peak, not kernel high-water mark",
                    "timestamp_convention" to "requested source-relative milliseconds; decoder exact PTS unavailable; intervals are left-anchored sample cells").toString() + "\n")
                val thresholds = QualityThresholds.bundled(this@BenchmarkActivity)
                val quality = QualityAnalyzer(thresholds)
                val hands = HandsAnalyzer(this@BenchmarkActivity)
                val items = plan.getJSONArray("items")
                val repeats = plan.optInt("repeats", 1).also { require(it in 1..20) }
                for (repeat in 0 until repeats) for (i in 0 until items.length()) {
                    ensureActive()
                    val item = items.getJSONObject(i)
                    val id = item.getString("id"); val name = item.getString("filename")
                    require(id.matches(Regex("[A-Za-z0-9_-]{1,80}")))
                    require(name.matches(Regex("[A-Za-z0-9_.-]{1,100}")) && !name.contains(".."))
                    val file = File(filesDir, "dataset/$name")
                    val digest = MessageDigest.getInstance("SHA-256")
                    file.inputStream().use { input -> val buffer = ByteArray(65536)
                        while (true) { val n = input.read(buffer); if (n < 0) break; digest.update(buffer, 0, n) } }
                    require(digest.digest().joinToString("") { "%02x".format(it) } == item.getString("sha256"))
                    val video = item.getString("kind") == "video"
                    val itemStart = System.nanoTime()
                    val q = if (video) quality.video(file) else quality.photo(file) { gray ->
                        if (plan.optBoolean("export_photo_gray", false)) {
                            File(reports, "$runId-$id.gray").writeBytes(gray.pixels)
                        }
                    }
                    output.appendText(qualityJson(q).put("id", id).put("repeat", repeat).toString() + "\n")
                    if (item.optBoolean("hands", video)) {
                        val h = if (video) hands.video(file) else hands.photo(file)
                        output.appendText(handsJson(h).put("id", id).put("repeat", repeat).toString() + "\n")
                    }
                    output.appendText(obj("type" to "item_end_to_end", "id" to id, "repeat" to repeat,
                        "duration_ms" to q.durationMs, "wall_ms" to QualityAnalyzer.elapsed(itemStart)).toString() + "\n")
                    withContext(Dispatchers.Main) { status.text = "Completed ${i + 1}/${items.length()}, repeat ${repeat + 1}." }
                }
                finalStatus = "COMPLETED" // Results retain independent module statuses; completion is not acceptance.
            }
        } catch (cancelled: CancellationException) { finalStatus = "CANCELLED" }
        catch (error: Exception) { failure = error.javaClass.simpleName + ":" + (error.message ?: "") }
        catch (_: OutOfMemoryError) { failure = "memory_pressure" }
        finally {
            withContext(NonCancellable) {
                memoryJob.cancelAndJoin()
                done.writeText(obj("run_id" to runId, "status" to finalStatus, "error" to failure,
                    "wall_ms" to QualityAnalyzer.elapsed(started), "observed_peak_pss_kb" to peakPssKb,
                    "observed_peak_native_bytes" to peakNativeBytes, "memory_samples" to memorySamples).toString(2) + "\n")
                status.text = "$finalStatus. Results are in private harness storage."
            }
        }
    }
    override fun onDestroy() { scope.cancel(); super.onDestroy() }
}
