package `in`.kaushalpramaan.app.data

import `in`.kaushalpramaan.app.data.draft.EvidenceDraftEntity
import `in`.kaushalpramaan.app.data.draft.EvidenceDraftState
import `in`.kaushalpramaan.app.data.draft.SealState
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

/** Evidence stays editable (retake/replace/delete/trim/add) throughout
 * DRAFT_EDITABLE/PROCESSING/FINAL_REVIEW_READY -- the worker can keep refining right up to
 * the moment they actually seal. It only becomes immutable in normal worker flow (spec part
 * E.3) once a seal attempt is genuinely underway or complete: SEAL_IN_PROGRESS, VAULT_READY,
 * READY_TO_SYNC. (Editing during FINAL_REVIEW_READY correctly invalidates it back to
 * DRAFT_EDITABLE -- see SealOrchestrator's capture/delete/trim hooks.) */
fun SealState.isEditable(): Boolean =
    this != SealState.SEAL_IN_PROGRESS && this != SealState.VAULT_READY && this != SealState.READY_TO_SYNC

enum class EvidenceType { PHOTO, VIDEO }

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

    // P5: seal state machine + attestation, mirrored live from the active AssessmentDraft
    // (see SealOrchestrator/AppViewModel.observeDraft) -- never a locally-faked flag.
    val sealState: SealState = SealState.DRAFT_EDITABLE,
    val attestationConfirmed: Boolean = false,
    val sealedAtMillis: Long? = null,
    // P6: current revision id (needed to address the right WorkManager unique-work name) and
    // final synced/submitted timestamp -- both mirrored live from the active AssessmentDraft,
    // same "never a locally-faked flag" discipline as sealState/attestationConfirmed above.
    val revisionId: String? = null,
    val syncedAtMillis: Long? = null,
    /** True while a processEvidence()/seal() call is in flight, for disabling buttons --
     * distinct from [sealState] == PROCESSING, which can also be true on resume before the
     * worker has tapped anything this session. */
    val sealActionInFlight: Boolean = false,
    /** Debug-build-only (`P5_TEST_ONLY`) forced virtual remaining-budget override, see
     * CaptureScreen's equivalent P4_TEST_ONLY pattern. Null means "not active" (use real
     * budgets). */
    val debugForcedBudgetBytes: Long? = null,
) {
    /** The real current byte footprint of one task's READY evidence: the FINAL
     * (post-optimisation) size once known, the raw captured size otherwise. Deliberately
     * computed live from [evidenceByTask] rather than trusting [TaskDraftEntity
     * .capturedBytes] (P4's own cached sum, which only ever reflects raw capture bytes and
     * goes stale the moment P5 optimisation/trim changes an item's effective size) -- every
     * screen that shows a budget bar must agree with the P5 ledger, never show a value above
     * its configured maximum because of a stale cache. */
    fun taskEvidenceBytes(taskId: String): Long =
        evidenceByTask[taskId].orEmpty()
            .filter { it.state == EvidenceDraftState.READY }
            .sumOf { it.finalBytes ?: it.byteSize }

    fun totalEvidenceBytes(): Long = taskDrafts.keys.sumOf { taskEvidenceBytes(it) }
}
