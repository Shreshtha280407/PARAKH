package `in`.kaushalpramaan.app.data.assistance

import android.content.Context
import androidx.room.withTransaction
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import `in`.kaushalpramaan.app.data.draft.AppDatabase
import `in`.kaushalpramaan.app.data.draft.EvidenceFileManager
import `in`.kaushalpramaan.assist.quality.*
import `in`.kaushalpramaan.assist.hands.*
import `in`.kaushalpramaan.core.seal.*
import java.io.File
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext

class EvidenceAssistanceWorker @JvmOverloads constructor(
    context: Context, params: WorkerParameters, private val database: AppDatabase? = null,
) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val evidenceId = inputData.getString("evidenceId") ?: return@withContext Result.failure()
        val generation = inputData.getString("generation") ?: return@withContext Result.failure()
        val db = database ?: AppDatabase.getInstance(applicationContext)
        val runner = AssistanceRunner(db, EvidenceFileManager(applicationContext), OnDeviceAssistance(applicationContext))
        try {
            runner.run(evidenceId, generation)
            Result.success()
        } catch (cancelled: CancellationException) {
            // Leave RUNNING durably: WorkManager reschedules process interruption; launch
            // recovery also queues it. A user cancellation changes the generation first.
            throw cancelled
        } catch (_: Exception) {
            runner.fail(evidenceId, generation, retry = runAttemptCount < 2)
            if (runAttemptCount < 2) Result.retry() else Result.success()
        }
    }
}

fun interface AssistanceEngine {
    suspend fun analyse(record: AssistanceRecord, file: File, onStage: suspend (String) -> Unit): AssistanceSnapshot
}

/** Testable lifecycle guard used by the real worker. No evidence row is rewritten by an
 * inference completion, so concurrent P5 updates cannot be lost through an old row copy. */
class AssistanceRunner(private val db: AppDatabase, private val files: EvidenceFileManager, private val engine: AssistanceEngine) {
    private suspend fun current(id: String, generation: String): AssistanceRecord? {
        val record = db.assistanceDao().get(id) ?: return null
        val item = db.evidenceDraftDao().getById(id) ?: return null
        val parent = db.assessmentDraftDao().getById(item.assessmentId) ?: return null
        return record.takeIf { it.generation == generation && it.revisionNumber == parent.currentRevisionNumber &&
            EvidenceAssistanceCoordinator.editable(item, parent) && it.inputPath == EvidenceAssistanceCoordinator.inputPath(item) }
    }

    suspend fun run(id: String, generation: String) = nativePermit.withPermit {
        val record = db.withTransaction {
            val candidate = current(id, generation) ?: return@withTransaction null
            if (candidate.status !in setOf("QUEUED", "RUNNING")) return@withTransaction null
            candidate.copy(status = "RUNNING", stage = "quality").also { db.assistanceDao().put(it) }
        } ?: return@withPermit
        val file = files.resolveRelativePath(record.inputPath)
        if (!file.isFile) { fail(id, generation, false, AssistanceError.MEDIA_UNAVAILABLE); return@withPermit }
        if (StreamingHasher.sha256Hex(file) != record.inputSha256) {
            fail(id, generation, false, AssistanceError.INPUT_CHANGED); return@withPermit
        }
        val result = engine.analyse(record, file) { stage ->
            db.withTransaction { current(id, generation)?.let { db.assistanceDao().put(it.copy(stage = stage)) } }
        }
        currentCoroutineContext().ensureActive()
        if (!file.isFile || StreamingHasher.sha256Hex(file) != record.inputSha256) {
            fail(id, generation, false, AssistanceError.INPUT_CHANGED); return@withPermit
        }
        result.validateBinding(record.assessmentId, record.taskId, id, record.inputSha256, record.durationMs)
        db.withTransaction {
            current(id, generation)?.let { live ->
                db.assistanceDao().put(live.copy(status = result.status.name, stage = "finished",
                    resultJson = EvidenceAssistanceCoordinator.JSON.encodeToString(AssistanceSnapshot.serializer(), result),
                    errorCategory = result.errorCategory?.name))
            }
        }
    }

    suspend fun fail(id: String, generation: String, retry: Boolean, error: AssistanceError = AssistanceError.ANALYSIS_FAILED) {
        db.withTransaction {
            current(id, generation)?.let { db.assistanceDao().put(it.copy(status = if (retry) "QUEUED" else "FAILED",
                stage = if (retry) "retrying" else "failed", resultJson = null, errorCategory = error.name)) }
        }
    }

    companion object { private val nativePermit = Semaphore(1) }
}

class OnDeviceAssistance(context: Context) : AssistanceEngine {
    private val quality by lazy { QualityAnalyzer.bundled(context) }
    private val hands by lazy { HandsAnalyzer(context) }

    override suspend fun analyse(record: AssistanceRecord, file: File, onStage: suspend (String) -> Unit): AssistanceSnapshot {
        val video = record.durationMs != null
        val q = if (video) quality.video(file) else quality.photo(file)
        onStage("hands")
        val h = if (video) hands.video(file) else null
        val qualityAnalysis = AssistanceAnalysis(q.status.wire(),
            if (q.thresholdVersion != null && q.thresholdSha256 != null) AssistanceProvenance(q.moduleVersion, q.thresholdVersion!!, q.thresholdSha256!!) else null,
            AssistanceCoverage(q.requestedSampleCount, q.analysedSampleCount,
                q.analysedDurationMs.coerceAtMost(record.durationMs ?: 0), q.motionRequestedPairCount, q.motionAnalysedPairCount), q.badCapture)
        val handAnalysis = h?.let {
            AssistanceAnalysis(it.status.wire(),
                if (it.modelSha256.matches(Regex("[0-9a-f]{64}")) && it.configurationSha256.matches(Regex("[0-9a-f]{64}")))
                    AssistanceProvenance(it.moduleVersion, it.modelVersion, it.configurationSha256, it.modelSha256, it.sampleIntervalMs) else null,
                AssistanceCoverage(it.samples.size, it.summary.analysedCount, it.summary.coveredDurationMs.coerceAtMost(record.durationMs ?: 0)),
                visibleRatio = it.summary.visibleRatio, visibleRatioGapFilled = it.summary.visibleRatioGapFilled)
        }
        val flags = mutableListOf<AssistanceFlag>()
        if (video) {
            q.intervals.forEach { (condition, ranges) -> ranges.forEach { range ->
                val end = minOf(range.endMs, record.durationMs!!)
                if (range.startMs < end) flags += AssistanceFlag(AssistanceFlagType.valueOf(condition.name), range.startMs, end)
            } }
            h?.summary?.handsNotVisibleIntervalsGapFilled?.forEach { range ->
                val end = minOf(range.endMs, record.durationMs!!)
                if (range.startMs < end) flags += AssistanceFlag(AssistanceFlagType.HANDS_NOT_DETECTED, range.startMs, end)
            }
        } else q.samples.firstOrNull()?.flags?.forEach { flags += AssistanceFlag(AssistanceFlagType.valueOf(it.condition.name), observed = it.observed, threshold = it.threshold) }
        val components = listOfNotNull(qualityAnalysis, handAnalysis)
        val truncated = flags.size > 256
        val status = when {
            truncated -> AssistanceStatus.PARTIAL
            components.all { it.status == AssistanceStatus.COMPLETED } -> AssistanceStatus.COMPLETED
            components.any { it.status in setOf(AssistanceStatus.COMPLETED, AssistanceStatus.PARTIAL) } -> AssistanceStatus.PARTIAL
            components.any { it.status == AssistanceStatus.UNAVAILABLE } -> AssistanceStatus.UNAVAILABLE
            else -> AssistanceStatus.FAILED
        }
        return AssistanceSnapshot(assessmentId = record.assessmentId, taskId = record.taskId, evidenceId = record.evidenceId,
            revisionId = "unsealed", revisionNumber = record.revisionNumber, mediaSha256 = record.inputSha256,
            durationMs = record.durationMs, status = status, quality = qualityAnalysis, hands = handAnalysis,
            flags = flags.distinct().sortedWith(compareBy({ it.type.name }, { it.startMs })).take(256), completedAtMillis = System.currentTimeMillis(),
            errorCategory = when { truncated -> AssistanceError.PAYLOAD_LIMIT
                status == AssistanceStatus.PARTIAL -> AssistanceError.INCOMPLETE_COVERAGE
                status == AssistanceStatus.UNAVAILABLE -> AssistanceError.MODEL_UNAVAILABLE
                status == AssistanceStatus.FAILED -> AssistanceError.ANALYSIS_FAILED
                else -> null }, intervalsTruncated = truncated)
    }

    private fun AnalysisStatus.wire() = when (this) {
        AnalysisStatus.SUCCESS -> AssistanceStatus.COMPLETED
        AnalysisStatus.PARTIAL -> AssistanceStatus.PARTIAL
        AnalysisStatus.FAILED -> AssistanceStatus.FAILED
        AnalysisStatus.UNAVAILABLE -> AssistanceStatus.UNAVAILABLE
    }
}
