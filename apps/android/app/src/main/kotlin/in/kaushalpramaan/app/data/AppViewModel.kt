package `in`.kaushalpramaan.app.data

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.core.mapping.Matcher
import `in`.kaushalpramaan.core.mapping.Rules
import `in`.kaushalpramaan.core.mapping.RulesLoader
import androidx.lifecycle.ViewModel
import java.util.UUID
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update

/**
 * Single in-memory source of truth for the whole P-3 flow. No Room, no disk
 * persistence, no network -- offline-first and ViewModel-scoped only (see
 * AppUiState's doc comment and docs/gates/P3.md).
 */
class AppViewModel : ViewModel() {

    val rules: Rules by lazy { RulesLoader.load() }

    private val _uiState = MutableStateFlow(AppUiState())
    val uiState: StateFlow<AppUiState> = _uiState

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

    /** Adds one mock evidence item, enforcing both the per-task and total
     * evidence budgets. Returns true on success; on failure, sets a
     * localized error message in uiState and changes nothing else. */
    fun addEvidence(taskId: String, type: EvidenceType, fakeSizeBytes: Long, nowMillis: Long): Boolean {
        val state = _uiState.value
        val taskBudget = taskBudgetBytes(taskId)
        val totalBudget = totalBudgetBytes()
        val newTaskTotal = state.taskEvidenceBytes(taskId) + fakeSizeBytes
        val newGrandTotal = state.totalEvidenceBytes() + fakeSizeBytes

        if (newTaskTotal > taskBudget) {
            _uiState.update { it.copy(lastErrorMessageRes = R.string.add_evidence_error_task_budget) }
            return false
        }
        if (newGrandTotal > totalBudget) {
            _uiState.update { it.copy(lastErrorMessageRes = R.string.add_evidence_error_total_budget) }
            return false
        }

        val item = MockEvidence(
            id = UUID.randomUUID().toString(),
            taskId = taskId,
            type = type,
            fakeSizeBytes = fakeSizeBytes,
            createdAtMillis = nowMillis,
        )
        _uiState.update { s ->
            val updated = s.evidenceByTask.toMutableMap()
            updated[taskId] = updated[taskId].orEmpty() + item
            s.copy(evidenceByTask = updated, lastErrorMessageRes = null)
        }
        return true
    }

    fun removeEvidence(taskId: String, evidenceId: String) {
        _uiState.update { s ->
            val updated = s.evidenceByTask.toMutableMap()
            updated[taskId] = updated[taskId].orEmpty().filterNot { it.id == evidenceId }
            s.copy(evidenceByTask = updated)
        }
    }

    /** Replace = remove the old item then add the new one, atomically from the
     * UI's point of view, with the SAME budget checks addEvidence uses (so a
     * replace that would blow the budget is rejected, not silently applied). */
    fun replaceEvidence(taskId: String, oldEvidenceId: String, type: EvidenceType, fakeSizeBytes: Long, nowMillis: Long): Boolean {
        val state = _uiState.value
        val old = state.evidenceByTask[taskId].orEmpty().firstOrNull { it.id == oldEvidenceId } ?: return false
        val taskBudget = taskBudgetBytes(taskId)
        val totalBudget = totalBudgetBytes()
        val newTaskTotal = state.taskEvidenceBytes(taskId) - old.fakeSizeBytes + fakeSizeBytes
        val newGrandTotal = state.totalEvidenceBytes() - old.fakeSizeBytes + fakeSizeBytes

        if (newTaskTotal > taskBudget) {
            _uiState.update { it.copy(lastErrorMessageRes = R.string.add_evidence_error_task_budget) }
            return false
        }
        if (newGrandTotal > totalBudget) {
            _uiState.update { it.copy(lastErrorMessageRes = R.string.add_evidence_error_total_budget) }
            return false
        }

        val replacement = old.copy(id = UUID.randomUUID().toString(), type = type, fakeSizeBytes = fakeSizeBytes, createdAtMillis = nowMillis)
        _uiState.update { s ->
            val updated = s.evidenceByTask.toMutableMap()
            updated[taskId] = updated[taskId].orEmpty().map { if (it.id == oldEvidenceId) replacement else it }
            s.copy(evidenceByTask = updated, lastErrorMessageRes = null)
        }
        return true
    }

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
}
