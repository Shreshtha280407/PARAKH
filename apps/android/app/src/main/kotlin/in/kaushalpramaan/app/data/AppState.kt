package `in`.kaushalpramaan.app.data

import `in`.kaushalpramaan.app.data.draft.EvidenceDraftEntity
import `in`.kaushalpramaan.app.data.draft.TaskDraftEntity
import `in`.kaushalpramaan.core.mapping.MatchOutput
import java.util.Locale

/**
 * Declaration, consent, registration and the live match computation remain
 * in-memory, ViewModel-scoped only -- unchanged from P-3 (see docs/gates/P3.md).
 * Evidence capture state (taskDrafts/evidenceByTask below) is P4: it mirrors
 * Room-backed, SQLCipher-encrypted drafts (see data/draft/EvidenceRepository.kt)
 * and survives process death and reboot. Everything else still resets on a
 * fresh process start, same accepted P-3 boundary as before.
 */

enum class AppLanguage(val localeTag: String) {
    ENGLISH("en"),
    HINDI("hi"),
    ;

    fun toLocale(): Locale = Locale.forLanguageTag(localeTag)
}

enum class EvidenceType { PHOTO, VIDEO }

enum class SubmissionState { NOT_SUBMITTED, SEALED_LOCALLY }

data class WorkerRegistration(
    val workerId: String,
    val phone: String,
    val pin: String,
)

data class DeclarationState(
    val answers: Map<String, String> = emptyMap(),
    val yearsOfExperience: Int = 0,
    val freeText: String = "",
    // Non-scored, informational-only signals for the assessor's context (see
    // DeclarationLabels.kt's WorkSettingOptions/PriorTrainingOptions). Neither
    // field is ever read by Matcher.match -- see AppViewModel.computeMatch(),
    // which only passes answers and freeText to the matcher.
    val workSetting: String? = null,
    val priorTraining: String? = null,
)

data class AppUiState(
    val language: AppLanguage = AppLanguage.ENGLISH,
    val consentAcknowledged: Boolean = false,
    val registration: WorkerRegistration? = null,
    val declaration: DeclarationState = DeclarationState(),
    val matchOutput: MatchOutput? = null,
    val attestationChecked: Boolean = false,
    val submissionState: SubmissionState = SubmissionState.NOT_SUBMITTED,
    val lastErrorMessageRes: Int? = null,

    // P4 durable draft state -- see EvidenceRepository. startRouteResolved flips to true
    // once the one-time launch reconciliation + active-draft lookup finishes; the nav
    // graph shows a brief loading screen until then rather than guessing a start route.
    val startRouteResolved: Boolean = false,
    val resumedFromDraft: Boolean = false,
    val assessmentDraftId: String? = null,
    val assessmentIsTestOnly: Boolean = true,
    val gapTaskIds: Set<String> = emptySet(),
    val taskDrafts: Map<String, TaskDraftEntity> = emptyMap(),
    val evidenceByTask: Map<String, List<EvidenceDraftEntity>> = emptyMap(),
) {
    fun totalEvidenceBytes(): Long = taskDrafts.values.sumOf { it.capturedBytes }

    fun taskEvidenceBytes(taskId: String): Long = taskDrafts[taskId]?.capturedBytes ?: 0L
}
