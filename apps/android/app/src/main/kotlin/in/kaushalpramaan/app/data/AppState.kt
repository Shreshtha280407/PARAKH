package `in`.kaushalpramaan.app.data

import `in`.kaushalpramaan.core.mapping.MatchOutput
import java.util.Locale

/**
 * P-3 scope: in-memory, ViewModel-scoped app state only. No Room, no disk
 * persistence, no encryption -- those are later phases (see
 * docs/gates/P3.md's explicit out-of-scope list). State survives
 * configuration changes (rotation) via ViewModel, not process death; that
 * is an accepted P-3 limitation, not a bug.
 */

enum class AppLanguage(val localeTag: String) {
    ENGLISH("en"),
    HINDI("hi"),
    ;

    fun toLocale(): Locale = Locale.forLanguageTag(localeTag)
}

enum class EvidenceType { PHOTO, VIDEO }

data class MockEvidence(
    val id: String,
    val taskId: String,
    val type: EvidenceType,
    val fakeSizeBytes: Long,
    val createdAtMillis: Long,
    val ready: Boolean = true,
)

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
)

data class AppUiState(
    val language: AppLanguage = AppLanguage.ENGLISH,
    val consentAcknowledged: Boolean = false,
    val registration: WorkerRegistration? = null,
    val declaration: DeclarationState = DeclarationState(),
    val matchOutput: MatchOutput? = null,
    val evidenceByTask: Map<String, List<MockEvidence>> = emptyMap(),
    val attestationChecked: Boolean = false,
    val submissionState: SubmissionState = SubmissionState.NOT_SUBMITTED,
    val lastErrorMessageRes: Int? = null,
) {
    fun totalEvidenceBytes(): Long = evidenceByTask.values.sumOf { list -> list.sumOf { it.fakeSizeBytes } }

    fun taskEvidenceBytes(taskId: String): Long = evidenceByTask[taskId].orEmpty().sumOf { it.fakeSizeBytes }
}
