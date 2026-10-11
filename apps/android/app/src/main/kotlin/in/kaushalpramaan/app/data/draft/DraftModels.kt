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
)
