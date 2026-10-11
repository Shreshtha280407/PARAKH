package `in`.kaushalpramaan.app.data

import `in`.kaushalpramaan.app.data.draft.AppDatabase
import `in`.kaushalpramaan.app.data.draft.BeginCaptureResult
import `in`.kaushalpramaan.app.data.draft.EvidenceDraftEntity
import `in`.kaushalpramaan.app.data.draft.EvidenceFileManager
import `in`.kaushalpramaan.app.data.draft.EvidenceRepository
import `in`.kaushalpramaan.app.data.draft.FinalizeResult
import `in`.kaushalpramaan.core.mapping.Matcher
import `in`.kaushalpramaan.core.mapping.Rules
import `in`.kaushalpramaan.core.mapping.RulesLoader
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

    private val _uiState = MutableStateFlow(AppUiState())
    val uiState: StateFlow<AppUiState> = _uiState

    init {
        viewModelScope.launch {
            repository.reconcileOnLaunch()
            val active = repository.getActiveAssessment()
            if (active != null) {
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
    ): FinalizeResult = repository.finalizeCapture(evidenceId, success, widthPx, heightPx, durationMillis)

    suspend fun cancelCapture(evidenceId: String) = repository.cancelCapture(evidenceId)

    suspend fun deleteEvidence(evidenceId: String) = repository.deleteEvidence(evidenceId)

    fun hasEnoughFreeSpace(): Boolean = repository.hasEnoughFreeSpace()

    fun evidenceFile(evidence: EvidenceDraftEntity) = repository.resolveFile(evidence)

    fun clearError() {
        _uiState.update { it.copy(lastErrorMessageRes = null) }
    }

    fun setAttestation(checked: Boolean) {
        _uiState.update { it.copy(attestationChecked = checked) }
    }

    fun submit() {
        if (!_uiState.value.attestationChecked) return
        _uiState.update { it.copy(submissionState = SubmissionState.SEALED_LOCALLY) }
    }

    /** Full P4_TEST_ONLY cleanup path: removes the draft's DB rows and every private file
     * under it, then resets in-memory state back to a fresh start. */
    fun deleteCurrentAssessmentDraft(onDone: () -> Unit) {
        val assessmentId = _uiState.value.assessmentDraftId ?: return
        viewModelScope.launch {
            repository.deleteAssessment(assessmentId)
            _uiState.value = AppUiState(startRouteResolved = true)
            onDone()
        }
    }
}
