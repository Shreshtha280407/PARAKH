package `in`.kaushalpramaan.app.data

import `in`.kaushalpramaan.app.BuildConfig
import `in`.kaushalpramaan.app.data.draft.AppDatabase
import `in`.kaushalpramaan.app.data.draft.BeginCaptureResult
import `in`.kaushalpramaan.app.data.draft.EvidenceDraftEntity
import `in`.kaushalpramaan.app.data.draft.EvidenceFileManager
import `in`.kaushalpramaan.app.data.draft.EvidenceRepository
import `in`.kaushalpramaan.app.data.draft.FinalizeResult
import `in`.kaushalpramaan.app.data.draft.OutboxItemEntity
import `in`.kaushalpramaan.app.data.draft.SealState
import `in`.kaushalpramaan.app.data.seal.ProcessOutcome
import `in`.kaushalpramaan.app.data.seal.SealOrchestrator
import `in`.kaushalpramaan.app.data.seal.SealOutcome
import `in`.kaushalpramaan.app.data.sync.SyncWorker
import `in`.kaushalpramaan.app.data.sync.WorkerUpdatesPollResult
import `in`.kaushalpramaan.app.data.sync.WorkerUpdatesRepository
import `in`.kaushalpramaan.app.data.sync.WorkerUpdatesWorker
import `in`.kaushalpramaan.app.data.sync.provideSyncEndpointConfig
import `in`.kaushalpramaan.core.mapping.Matcher
import `in`.kaushalpramaan.core.mapping.Rules
import `in`.kaushalpramaan.core.mapping.RulesLoader
import `in`.kaushalpramaan.core.seal.VaultKeysetProvider
import `in`.kaushalpramaan.media.PhotoOptimizer
import `in`.kaushalpramaan.media.VideoOptimizer
import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import java.util.UUID
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Single source of truth for the whole worker flow. Declaration/consent/registration/match
 * stay in-memory and ViewModel-scoped (P-3 behaviour, unchanged). Evidence capture
 * (taskDrafts/evidenceByTask) is backed by [EvidenceRepository] -- Room, SQLCipher-encrypted,
 * app-private files on disk (P4) -- and survives process death/reboot. No network calls
 * anywhere in this class or anything it owns.
 */
class AppViewModel(application: Application) : AndroidViewModel(application) {

    val rules: Rules by lazy { RulesLoader.load() }

    private val database by lazy { AppDatabase.getInstance(application) }
    private val fileManager by lazy { EvidenceFileManager(application) }
    val repository: EvidenceRepository by lazy {
        EvidenceRepository(
            assessmentDraftDao = database.assessmentDraftDao(),
            taskDraftDao = database.taskDraftDao(),
            evidenceDraftDao = database.evidenceDraftDao(),
            fileManager = fileManager,
            rules = rules,
        )
    }
    private val sealOrchestrator: SealOrchestrator by lazy {
        SealOrchestrator(
            assessmentDraftDao = database.assessmentDraftDao(),
            evidenceDraftDao = database.evidenceDraftDao(),
            outboxDao = database.outboxDao(),
            fileManager = fileManager,
            rules = rules,
            photoOptimizer = PhotoOptimizer(),
            videoOptimizer = VideoOptimizer(application),
            vaultKeysetProvider = VaultKeysetProvider(application),
            appVersion = BuildConfig.VERSION_NAME,
        )
    }
    val debugExportHooks: `in`.kaushalpramaan.app.debug.DebugExportHooks by lazy {
        `in`.kaushalpramaan.app.debug.provideDebugExportHooks(database, fileManager, VaultKeysetProvider(application))
    }
    val syncEndpointConfig by lazy { provideSyncEndpointConfig(application) }
    private val workerUpdatesRepository: WorkerUpdatesRepository by lazy {
        WorkerUpdatesRepository(
            assessmentDraftDao = database.assessmentDraftDao(),
            taskDraftDao = database.taskDraftDao(),
            endpointConfig = syncEndpointConfig,
        )
    }

    private val _uiState = MutableStateFlow(AppUiState())
    val uiState: StateFlow<AppUiState> = _uiState

    init {
        viewModelScope.launch {
            repository.reconcileOnLaunch()
            val active = repository.getActiveAssessment()
            if (active != null) {
                sealOrchestrator.reconcileOnLaunch(active.id)
                val gapIds = active.gapTaskIdsCsv.split(",").map { it.trim() }.filter { it.isNotEmpty() }.toSet()
                val resumedLanguage = AppLanguage.entries.firstOrNull { it.localeTag == active.language } ?: AppLanguage.ENGLISH
                _uiState.update {
                    it.copy(
                        language = resumedLanguage,
                        registration = active.workerId?.let { workerId -> WorkerRegistration(workerId = workerId, phone = "", pin = "") },
                        assessmentDraftId = active.id,
                        assessmentIsTestOnly = active.isTestOnly,
                        gapTaskIds = gapIds,
                        resumedFromDraft = true,
                        startRouteResolved = true,
                    )
                }
                observeDraft(active.id)
            } else {
                _uiState.update { it.copy(startRouteResolved = true) }
            }
        }
    }

    fun setLanguage(language: AppLanguage) {
        _uiState.update { it.copy(language = language) }
    }

    fun setConsentAcknowledged(acknowledged: Boolean) {
        _uiState.update { it.copy(consentAcknowledged = acknowledged) }
    }

    fun register(phone: String, pin: String) {
        val workerId = "KP-" + UUID.randomUUID().toString().take(8).uppercase()
        _uiState.update { it.copy(registration = WorkerRegistration(workerId = workerId, phone = phone, pin = pin)) }
    }

    fun setAnswer(itemId: String, answer: String) {
        _uiState.update { state ->
            state.copy(declaration = state.declaration.copy(answers = state.declaration.answers + (itemId to answer)))
        }
    }

    fun setYearsOfExperience(years: Int) {
        _uiState.update { it.copy(declaration = it.declaration.copy(yearsOfExperience = years.coerceIn(0, 50))) }
    }

    fun setFreeText(text: String) {
        _uiState.update { it.copy(declaration = it.declaration.copy(freeText = text)) }
    }

    /** Non-scored, informational-only -- see DeclarationState's doc comment.
     * computeMatch() below never reads either of these two fields. */
    fun setWorkSetting(id: String) {
        _uiState.update { it.copy(declaration = it.declaration.copy(workSetting = id)) }
    }

    fun setPriorTraining(id: String) {
        _uiState.update { it.copy(declaration = it.declaration.copy(priorTraining = id)) }
    }

    /** Runs the on-device Kotlin matcher against the current declaration.
     * Pure local computation -- no network call is possible (see
     * app/build.gradle.kts's verifyNoNetworkDependencies task and the
     * instrumented test that asserts this). */
    fun computeMatch() {
        val declaration = _uiState.value.declaration
        val output = Matcher.match(answers = declaration.answers, freeText = declaration.freeText, rules = rules)
        _uiState.update { it.copy(matchOutput = output) }
    }

    fun taskBudgetBytes(taskId: String): Long =
        rules.tasksFile.tasks.firstOrNull { it.id == taskId }?.budgetBytes ?: 0L

    fun totalBudgetBytes(): Long = rules.tasksFile.finalEvidenceBudgetBytes

    /** Creates the one P4_TEST_ONLY draft on first arrival at the task list, or returns
     * the existing one unchanged if already created this session -- safe to call every
     * time the task list is opened. */
    fun startOrResumeAssessmentDraft() {
        if (_uiState.value.assessmentDraftId != null) return
        viewModelScope.launch {
            val state = _uiState.value
            val active = repository.createOrResumeAssessment(
                workerId = state.registration?.workerId,
                language = state.language.localeTag,
                matchOutput = state.matchOutput,
                declaration = state.declaration,
            )
            val gapIds = state.matchOutput?.applicableTasks
                ?.filter { it.extraEvidenceNeeded }
                ?.mapNotNull { it.task }
                ?.toSet()
                .orEmpty()
            _uiState.update {
                it.copy(assessmentDraftId = active.id, assessmentIsTestOnly = active.isTestOnly, gapTaskIds = gapIds)
            }
            observeDraft(active.id)
        }
    }

    private fun observeDraft(assessmentId: String) {
        viewModelScope.launch {
            repository.observeTasks(assessmentId).collect { list ->
                _uiState.update { it.copy(taskDrafts = list.associateBy { task -> task.taskId }) }
            }
        }
        for (task in rules.tasksFile.tasks) {
            viewModelScope.launch {
                repository.observeEvidenceForTask(assessmentId, task.id).collect { items ->
                    _uiState.update { it.copy(evidenceByTask = it.evidenceByTask + (task.id to items)) }
                }
            }
        }
        // P5 seal state machine + attestation -- live, never a locally-faked flag (see
        // SealOrchestrator, which is the only writer of these columns).
        viewModelScope.launch {
            repository.observeActiveAssessment().collect { assessment ->
                if (assessment != null && assessment.id == assessmentId) {
                    _uiState.update {
                        it.copy(
                            sealState = assessment.sealState,
                            attestationConfirmed = assessment.attestationConfirmed,
                            sealedAtMillis = assessment.sealedAtMillis,
                            revisionId = assessment.revisionId,
                            syncedAtMillis = assessment.syncedAtMillis,
                            currentRevisionNumber = assessment.currentRevisionNumber,
                            pendingReassessmentTaskCodes = assessment.pendingReassessmentTaskCodesCsv
                                ?.split(",")?.map { c -> c.trim() }?.filter { c -> c.isNotEmpty() }.orEmpty(),
                            pendingReassessmentReason = assessment.pendingReassessmentReason,
                            pendingReassessmentCaptureInstructions = assessment.pendingReassessmentCaptureInstructions,
                            reportStatus = assessment.reportStatus,
                        )
                    }
                    // P6: react to the package becoming ready (just sealed, or resumed already
                    // READY_TO_SYNC from a prior session) by enqueueing sync -- enqueueUniqueWork
                    // with ExistingWorkPolicy.KEEP (see SyncWorker.enqueue) makes this safe to
                    // call on every single emission, not just a detected transition.
                    if (assessment.sealState == SealState.READY_TO_SYNC &&
                        assessment.syncedAtMillis == null &&
                        assessment.revisionId != null
                    ) {
                        SyncWorker.enqueue(getApplication(), assessment.id, assessment.revisionId)
                    }
                    // P7: once this device has a server identity, start polling for
                    // reassessment requests/report status -- enqueueUniquePeriodicWork with
                    // KEEP (see WorkerUpdatesWorker.enqueuePeriodic) makes this safe on every
                    // emission too.
                    if (assessment.serverAssessmentId != null) {
                        WorkerUpdatesWorker.enqueuePeriodic(getApplication(), assessment.id)
                    }
                }
            }
        }
    }

    /** Manual "Sync now" -- safe to tap repeatedly (see SyncWorker.enqueue's doc comment); a
     * no-op while a sync attempt is already pending/running, and a genuine fresh retry once a
     * previous attempt has actually finished (succeeded, or failed and the worker fixed the
     * underlying problem with a new seal). */
    fun syncNow() {
        val state = _uiState.value
        val assessmentId = state.assessmentDraftId ?: return
        val revisionId = state.revisionId ?: return
        if (state.sealState != SealState.READY_TO_SYNC || state.syncedAtMillis != null) return
        SyncWorker.enqueue(getApplication(), assessmentId, revisionId)
    }

    /** P7: immediate, on-demand pull of GET /assessments/{id}/worker-updates -- the exact
     * same logic the periodic [WorkerUpdatesWorker] runs, exposed for a manual "Check for
     * updates" action so the worker doesn't have to wait up to 15 minutes (the WorkManager
     * periodic-work floor) to see a freshly-requested reassessment. */
    suspend fun checkForWorkerUpdates(): WorkerUpdatesPollResult {
        val assessmentId = _uiState.value.assessmentDraftId ?: return WorkerUpdatesPollResult.NoActiveAssessment
        return workerUpdatesRepository.pollAndApply(assessmentId)
    }

    private fun currentAssessmentId(): String =
        requireNotNull(_uiState.value.assessmentDraftId) { "assessment draft must exist before capture" }

    suspend fun beginCapture(taskId: String, type: EvidenceType, debugOverrideRequested: Boolean, replacesEvidenceId: String?): BeginCaptureResult =
        repository.beginCapture(currentAssessmentId(), taskId, type, debugOverrideRequested, replacesEvidenceId)

    suspend fun currentCeilingBytes(taskId: String, debugOverrideRequested: Boolean, replacesEvidenceId: String?): Long =
        repository.currentCeilingBytes(currentAssessmentId(), taskId, debugOverrideRequested, replacesEvidenceId)

    suspend fun finalizeCapture(
        evidenceId: String,
        success: Boolean,
        widthPx: Int? = null,
        heightPx: Int? = null,
        durationMillis: Long? = null,
    ): FinalizeResult {
        val result = repository.finalizeCapture(evidenceId, success, widthPx, heightPx, durationMillis)
        // A successful new/replacement capture invalidates a prior FINAL_REVIEW_READY --
        // see SealOrchestrator.invalidateFinalReviewIfNeeded's doc comment.
        if (result is FinalizeResult.Ready) sealOrchestrator.invalidateFinalReviewIfNeeded(currentAssessmentId())
        return result
    }

    suspend fun cancelCapture(evidenceId: String) = repository.cancelCapture(evidenceId)

    suspend fun deleteEvidence(evidenceId: String) {
        repository.deleteEvidence(evidenceId)
        sealOrchestrator.invalidateFinalReviewIfNeeded(currentAssessmentId())
    }

    fun hasEnoughFreeSpace(): Boolean = repository.hasEnoughFreeSpace()

    fun evidenceFile(evidence: EvidenceDraftEntity) = repository.resolveFile(evidence)

    fun clearError() {
        _uiState.update { it.copy(lastErrorMessageRes = null) }
    }

    // ---- P5: automatic optimisation, attestation, seal ----

    /** Runs the real automatic photo/video optimisation pass over every not-yet-processed
     * READY item (spec parts C/D). Safe to call repeatedly -- already-processed items are
     * skipped. */
    suspend fun processEvidence(): ProcessOutcome {
        _uiState.update { it.copy(sealActionInFlight = true) }
        return try {
            sealOrchestrator.processEvidence(currentAssessmentId(), _uiState.value.debugForcedBudgetBytes)
        } finally {
            _uiState.update { it.copy(sealActionInFlight = false) }
        }
    }

    /** Minimal offline video trim (spec part D.5) -- see SealOrchestrator.trimVideo. */
    suspend fun trimVideo(evidenceId: String, startMs: Long, endMs: Long): Boolean =
        sealOrchestrator.trimVideo(currentAssessmentId(), evidenceId, startMs, endMs)

    fun setAttestation(confirmed: Boolean) {
        viewModelScope.launch { sealOrchestrator.setAttestation(currentAssessmentId(), confirmed) }
    }

    /** Builds the canonical manifest, signs it with the device's non-exportable Keystore key,
     * encrypts every final item plus the manifest into the vault, commits the outbox, and
     * transitions to READY_TO_SYNC (spec parts F/G). No network call anywhere in this path.
     *
     * P7: once a targeted reassessment request is pending (see [checkForWorkerUpdates]),
     * this seals ONLY the reopened tasks' new evidence, re-declaring every other task's
     * already-verified evidence by reference (see
     * SealOrchestrator.sealTargetedRevision) -- never the plain [SealOrchestrator.seal],
     * which would otherwise try to re-seal (and so first re-hash/re-encrypt) evidence whose
     * local vault copy P6 already deleted after its original receipt. */
    suspend fun seal(): SealOutcome {
        _uiState.update { it.copy(sealActionInFlight = true) }
        val reopenedTasks = _uiState.value.pendingReassessmentTaskCodes.toSet()
        return try {
            if (reopenedTasks.isNotEmpty()) {
                sealOrchestrator.sealTargetedRevision(currentAssessmentId(), reopenedTasks)
            } else {
                sealOrchestrator.seal(currentAssessmentId())
            }
        } finally {
            _uiState.update { it.copy(sealActionInFlight = false) }
        }
    }

    /** The only path back to an editable draft once sealing has started/completed (spec part
     * E.4) -- restores evidence from the vault if the seal had already reached READY_TO_SYNC,
     * then removes the local seal entirely. Requires explicit confirmation in the UI before
     * calling this; never invoked silently. */
    suspend fun discardSealAndReopen() {
        val assessmentId = currentAssessmentId()
        // Capture the revision being abandoned BEFORE discarding -- discardAndReopen assigns a
        // fresh one, and a live sync attempt for the OLD revision must be stopped immediately
        // rather than waiting for its next network round-trip to notice (see SyncWorker.cancel
        // and SyncRepository.syncAssessment's own sealState/revisionId no-op check).
        val oldRevisionId = _uiState.value.revisionId
        sealOrchestrator.discardAndReopen(assessmentId)
        if (oldRevisionId != null) {
            SyncWorker.cancel(getApplication(), assessmentId, oldRevisionId)
        }
    }

    fun observeOutbox(assessmentId: String) = database.outboxDao().observeForAssessment(assessmentId)

    /** Debug-build-only (`P5_TEST_ONLY`): forces the budget ledger to treat the assessment as
     * having only [bytes] of total room left, routed through the exact same production
     * BudgetLedger/optimisation path as real budgets -- never a separate mock path. Null
     * clears the override. No-op outside debug builds (callers only render the toggle when
     * `BuildConfig.P5_TEST_ONLY_FORCE_OPTIMIZE_ENABLED` is true). */
    fun setDebugForcedBudgetBytes(bytes: Long?) {
        if (!BuildConfig.P5_TEST_ONLY_FORCE_OPTIMIZE_ENABLED) return
        _uiState.update { it.copy(debugForcedBudgetBytes = bytes) }
    }

    /** Full P4_TEST_ONLY cleanup path: removes the draft's DB rows and every private file
     * under it (including any P5 vault/outbox state), then resets in-memory state back to a
     * fresh start. */
    fun deleteCurrentAssessmentDraft(onDone: () -> Unit) {
        val assessmentId = _uiState.value.assessmentDraftId ?: return
        viewModelScope.launch {
            repository.deleteAssessment(assessmentId)
            _uiState.value = AppUiState(startRouteResolved = true)
            onDone()
        }
    }
}
