package `in`.kaushalpramaan.app.data.draft

import `in`.kaushalpramaan.app.data.EvidenceType
import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey

/**
 * P4 durable local draft schema (Room, SQLCipher-encrypted -- see AppDatabase.kt).
 * Everything created through this layer in this phase is a P4_TEST_ONLY capture
 * drill: there is no real assessment submission, scoring, or upload built on top
 * of it yet (that is P5/P6, intentionally not implemented here).
 */

/** [ACTIVE] is the normal state for the one open draft. [DELETED] is a transient,
 * crash-safe marker written before any file/row removal starts; if the app dies
 * mid-delete, launch-time reconciliation finds [DELETED] rows and finishes the
 * job rather than leaving an inconsistent half-deleted draft. */
enum class AssessmentDraftState { ACTIVE, DELETED }

/** P5's own crash-safe seal state machine (spec part G.6), orthogonal to
 * [AssessmentDraftState] (which only ever means "the active draft" vs "removed"):
 * [DRAFT_EDITABLE] -- normal P4-style editing; evidence can be captured/retaken/replaced/
 * deleted freely. [PROCESSING] -- automatic photo/video optimisation is running against the
 * current evidence set. [FINAL_REVIEW_READY] -- every chosen item has a final (fits-budget)
 * representation; the worker can review and attest. [SEAL_IN_PROGRESS] -- manifest built,
 * signed, and evidence/manifest encryption into the vault is underway. [VAULT_READY] -- every
 * vault artifact is encrypted and verified on disk, but outbox rows are not committed yet.
 * [READY_TO_SYNC] -- outbox rows committed; the sealed package is complete, immutable in
 * normal worker flow, and ready for P6 (not implemented here) to eventually upload. */
enum class SealState { DRAFT_EDITABLE, PROCESSING, FINAL_REVIEW_READY, SEAL_IN_PROGRESS, VAULT_READY, READY_TO_SYNC }

/** Per-evidence-item automatic-optimisation progress (P5 spec part C/D), independent of the
 * P4 [EvidenceDraftState] lifecycle it sits alongside: [NOT_PROCESSED] -- still the raw P4
 * capture, no final representation decided yet. [FITS_AS_IS] -- the raw capture already fits
 * its budget; the final representation IS the raw file, byte-identical. [OPTIMIZED] -- a real
 * photo/video optimisation pass produced a smaller final file that fits. [QUALITY_FLOOR_EXCEEDED]
 * -- even the quality floor does not fit; a recoverable draft exists but this item blocks
 * sealing until the worker retakes/replaces/trims/removes it. [SEALED] -- this item's final
 * plaintext has been successfully encrypted into the vault and its raw/temp plaintext files
 * deleted (spec part G.5); only [EvidenceDraftEntity.vaultRelativePath] is still valid. */
enum class FinalEvidenceState { NOT_PROCESSED, FITS_AS_IS, OPTIMIZED, QUALITY_FLOOR_EXCEEDED, SEALED }

/** Derived from the task's own evidence rows and kept as a persisted column (not
 * recomputed only in memory) so it survives process death exactly: [NO_EVIDENCE]
 * (empty), [CAPTURING] (a STAGING evidence item exists), [READY] (at least one
 * READY item, nothing staging), [FAILED] (only FAILED items remain). */
enum class TaskDraftState { NO_EVIDENCE, CAPTURING, READY, FAILED }

/** [STAGING]: CameraX is writing (or was interrupted writing) to a temp file; not
 * yet promoted. [READY]: finalized, validated, atomically promoted, safe to
 * preview. [DELETED]: transient pre-removal marker, same crash-safety pattern as
 * [AssessmentDraftState.DELETED]. [FAILED]: capture/finalize failed, or launch-time
 * reconciliation found an unrecoverable STAGING row (process died mid-capture);
 * shown to the user, removable via the normal delete action. */
enum class EvidenceDraftState { STAGING, READY, DELETED, FAILED }

@Entity(tableName = "assessment_drafts")
data class AssessmentDraftEntity(
    @PrimaryKey val id: String,
    val state: AssessmentDraftState,
    val qpCode: String,
    val qpVersion: String,
    val workerId: String?,
    val language: String,
    @ColumnInfo(name = "match_result") val matchResult: String?,
    @ColumnInfo(name = "overall_coverage") val overallCoverage: Double?,
    /** Comma-separated T-ids with extraEvidenceNeeded==true at the time the match was
     * computed -- cached purely so a resumed task list can show the same gap badges
     * without re-running the declaration/matcher flow, which P4 does not persist. */
    @ColumnInfo(name = "gap_task_ids_csv") val gapTaskIdsCsv: String,
    @ColumnInfo(name = "is_test_only") val isTestOnly: Boolean,
    @ColumnInfo(name = "created_at_millis") val createdAtMillis: Long,
    @ColumnInfo(name = "updated_at_millis") val updatedAtMillis: Long,

    // ---- P5: seal state machine (see SealState) ----
    @ColumnInfo(name = "seal_state", defaultValue = "DRAFT_EDITABLE") val sealState: SealState = SealState.DRAFT_EDITABLE,
    /** Generated once, the first time this assessment is sealed (or re-sealed after an
     * explicit discard/reopen); stable across a single seal attempt's crash/resume, bumped
     * only by an explicit discard+reopen (spec part E.4). Null until first assigned. */
    @ColumnInfo(name = "revision_id") val revisionId: String? = null,
    @ColumnInfo(name = "attestation_confirmed", defaultValue = "0") val attestationConfirmed: Boolean = false,
    @ColumnInfo(name = "attestation_at_millis") val attestationAtMillis: Long? = null,
    @ColumnInfo(name = "sealed_at_millis") val sealedAtMillis: Long? = null,
    /** App-private relative path to the encrypted manifest+signature vault package, set once
     * VAULT_READY. */
    @ColumnInfo(name = "manifest_vault_relative_path") val manifestVaultRelativePath: String? = null,
    @ColumnInfo(name = "signer_key_id") val signerKeyId: String? = null,
    @ColumnInfo(name = "signer_public_key_base64") val signerPublicKeyBase64: String? = null,
    @ColumnInfo(name = "idempotency_key") val idempotencyKey: String? = null,
)

@Entity(
    tableName = "task_drafts",
    primaryKeys = ["assessmentId", "taskId"],
    foreignKeys = [
        ForeignKey(
            entity = AssessmentDraftEntity::class,
            parentColumns = ["id"],
            childColumns = ["assessmentId"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("assessmentId")],
)
data class TaskDraftEntity(
    val assessmentId: String,
    val taskId: String,
    val state: TaskDraftState,
    @ColumnInfo(name = "evidence_count") val evidenceCount: Int,
    /** Configured task safety budget, copied from the canonical packs/ae-con-q0602/tasks.json
     * entry (via core:mapping's Rules) at task-draft creation time -- cached, not a second
     * source of truth; P4 never edits QP/rubric/mapping content. */
    @ColumnInfo(name = "budget_bytes") val budgetBytes: Long,
    @ColumnInfo(name = "captured_bytes") val capturedBytes: Long,
    @ColumnInfo(name = "updated_at_millis") val updatedAtMillis: Long,
)

@Entity(
    tableName = "evidence_drafts",
    foreignKeys = [
        ForeignKey(
            entity = TaskDraftEntity::class,
            parentColumns = ["assessmentId", "taskId"],
            childColumns = ["assessmentId", "taskId"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("assessmentId"), Index(value = ["assessmentId", "taskId"])],
)
data class EvidenceDraftEntity(
    @PrimaryKey val id: String,
    val assessmentId: String,
    val taskId: String,
    val kind: EvidenceType,
    /** App-private relative path only (relative to Context.filesDir), e.g.
     * "drafts/<assessmentId>/<taskId>/<evidenceId>.jpg" -- never a MediaStore/Gallery URI. */
    @ColumnInfo(name = "relative_path") val relativePath: String,
    @ColumnInfo(name = "byte_size") val byteSize: Long,
    @ColumnInfo(name = "created_at_millis") val createdAtMillis: Long,
    @ColumnInfo(name = "width_px") val widthPx: Int?,
    @ColumnInfo(name = "height_px") val heightPx: Int?,
    @ColumnInfo(name = "duration_millis") val durationMillis: Long?,
    val state: EvidenceDraftState,
    /** Non-null only while this item is a replacement in flight: the id of the READY item
     * it will remove once this one reaches READY itself. Lets launch-time reconciliation
     * finish an interrupted replace by forward-recovery (finish deleting the old item)
     * instead of leaving two items where the UI expects one. */
    @ColumnInfo(name = "replaces_evidence_id") val replacesEvidenceId: String?,
    @ColumnInfo(name = "is_test_only") val isTestOnly: Boolean,
    /** Whether the debug-only P4_TEST_ONLY ceiling override was requested for this specific
     * capture, captured at beginCapture() time and replayed at finalizeCapture() time so the
     * fail-closed final-size check recomputes the exact same effective ceiling that was
     * active for this capture -- never a looser one. Always false in release builds (the
     * override itself cannot be enabled there; see BuildConfig.P4_TEST_ONLY_CEILING_ENABLED). */
    @ColumnInfo(name = "debug_ceiling_requested", defaultValue = "0") val debugCeilingRequested: Boolean = false,

    // ---- P5: per-item automatic-optimisation outcome (see FinalEvidenceState) ----
    @ColumnInfo(name = "final_state", defaultValue = "NOT_PROCESSED") val finalState: FinalEvidenceState = FinalEvidenceState.NOT_PROCESSED,
    /** Relative path to the final plaintext representation once processed -- equal to
     * [relativePath] when [finalState] is FITS_AS_IS (no separate file was written), a
     * distinct app-private temp file when OPTIMIZED/QUALITY_FLOOR_EXCEEDED. Null until
     * processed. Deleted once sealing succeeds (spec part G.5) -- only the encrypted vault
     * copy survives past a successful seal. */
    @ColumnInfo(name = "final_relative_path") val finalRelativePath: String? = null,
    @ColumnInfo(name = "final_bytes") val finalBytes: Long? = null,
    @ColumnInfo(name = "final_sha256") val finalSha256: String? = null,
    @ColumnInfo(name = "final_mime_type") val finalMimeType: String? = null,
    @ColumnInfo(name = "final_width_px") val finalWidthPx: Int? = null,
    @ColumnInfo(name = "final_height_px") val finalHeightPx: Int? = null,
    @ColumnInfo(name = "final_duration_millis") val finalDurationMillis: Long? = null,
    /** App-private relative path to this item's encrypted vault copy, set once sealing
     * reaches VAULT_READY for this item. */
    @ColumnInfo(name = "vault_relative_path") val vaultRelativePath: String? = null,
)

enum class OutboxItemKind { MANIFEST, EVIDENCE }

/** P5's durable outbox (spec part G.8): one row per vault artifact (the manifest package, plus
 * one per encrypted evidence item), created only once that artifact is genuinely VAULT_READY.
 * P5 itself never acts on these rows beyond creating them -- no HTTP, no WorkManager, no
 * polling (spec part G.9); P6 is the only consumer. */
@Entity(
    tableName = "outbox_items",
    foreignKeys = [
        ForeignKey(
            entity = AssessmentDraftEntity::class,
            parentColumns = ["id"],
            childColumns = ["assessmentId"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("assessmentId"), Index("idempotency_key")],
)
data class OutboxItemEntity(
    @PrimaryKey val id: String,
    val assessmentId: String,
    @ColumnInfo(name = "revision_id") val revisionId: String,
    /** Stable per-assessment-revision key future P6 upload de-duplicates against. */
    @ColumnInfo(name = "idempotency_key") val idempotencyKey: String,
    val kind: OutboxItemKind,
    /** Null for the MANIFEST row. */
    @ColumnInfo(name = "evidence_id") val evidenceId: String?,
    @ColumnInfo(name = "task_id") val taskId: String?,
    @ColumnInfo(name = "vault_relative_path") val vaultRelativePath: String,
    /** Manifest first (priority 0), then evidence (priority 1+) -- see spec part G.8. */
    val priority: Int,
    @ColumnInfo(name = "created_at_millis") val createdAtMillis: Long,
    /** Retry metadata placeholders only -- P5 never performs network I/O, so these are never
     * incremented or read by anything in this phase; they exist so P6 does not need its own
     * schema migration just to start recording attempts. */
    @ColumnInfo(name = "retry_count", defaultValue = "0") val retryCount: Int = 0,
    @ColumnInfo(name = "last_attempt_at_millis") val lastAttemptAtMillis: Long? = null,
)
