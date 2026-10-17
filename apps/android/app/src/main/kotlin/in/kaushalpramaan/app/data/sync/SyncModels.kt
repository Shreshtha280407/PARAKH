package `in`.kaushalpramaan.app.data.sync

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Plain DTOs for the P6 server API (server/app/schemas.py / routers/uploads.py,
 * routers/assessments.py's sync-status/submit) -- field names match the server's JSON
 * exactly (snake_case, FastAPI/Pydantic's default), never re-derived from the OpenAPI spec
 * at build time (no generated client exists on the Android side; kept hand-written and
 * minimal, same deliberate choice the dashboard's src/types.ts documents for the same
 * reason -- contracts/openapi.json is the authoritative contract, CI-checked fresh against
 * the real server).
 */

@Serializable
data class UploadSessionCreateRequest(
    @SerialName("assessment_id") val assessmentId: Long,
    val target: String, // "evidence" | "manifest"
    @SerialName("task_code") val taskCode: String? = null,
    val kind: String? = null,
    val mime: String? = null,
    @SerialName("claimed_size_bytes") val claimedSizeBytes: Long,
    @SerialName("revision_id") val revisionId: String? = null,
    @SerialName("client_evidence_id") val clientEvidenceId: String? = null,
)

@Serializable
data class UploadSessionOut(
    val id: Long,
    @SerialName("assessment_id") val assessmentId: Long,
    @SerialName("assessment_task_id") val assessmentTaskId: Long? = null,
    val target: String,
    val kind: String? = null,
    val mime: String? = null,
    @SerialName("claimed_size_bytes") val claimedSizeBytes: Long,
    @SerialName("received_bytes") val receivedBytes: Long,
    @SerialName("next_chunk_index") val nextChunkIndex: Int,
    val status: String,
    @SerialName("revision_id") val revisionId: String? = null,
    @SerialName("client_evidence_id") val clientEvidenceId: String? = null,
)

@Serializable
data class ChunkAck(
    @SerialName("chunk_index") val chunkIndex: Int,
    @SerialName("received_bytes") val receivedBytes: Long,
    @SerialName("next_chunk_index") val nextChunkIndex: Int,
    val status: String,
)

@Serializable
data class UploadCompleteRequest(
    @SerialName("client_sha256") val clientSha256: String,
)

@Serializable
data class UploadReceipt(
    @SerialName("session_id") val sessionId: Long,
    @SerialName("evidence_id") val evidenceId: Long,
    val sha256: String,
    @SerialName("byte_count") val byteCount: Long,
    val mime: String,
    val kind: String,
    @SerialName("storage_status") val storageStatus: String,
)

@Serializable
data class ManifestReceipt(
    @SerialName("session_id") val sessionId: Long,
    @SerialName("manifest_id") val manifestId: Long,
    @SerialName("assessment_id") val assessmentId: Long,
    @SerialName("revision_id") val revisionId: String,
    val sha256: String,
    @SerialName("item_count") val itemCount: Int,
    @SerialName("declared_total_bytes") val declaredTotalBytes: Long,
    val status: String, // "received" | "rejected"
    @SerialName("rejection_reason") val rejectionReason: String? = null,
)

@Serializable
data class SyncItemStatusOut(
    @SerialName("client_evidence_id") val clientEvidenceId: String,
    @SerialName("task_code") val taskCode: String,
    val kind: String,
    @SerialName("declared_bytes") val declaredBytes: Long,
    val state: String, // "pending" | "uploading" | "verified" | "rejected"
    @SerialName("received_bytes") val receivedBytes: Long? = null,
    @SerialName("upload_session_id") val uploadSessionId: Long? = null,
    @SerialName("evidence_id") val evidenceId: Long? = null,
    @SerialName("rejection_reason") val rejectionReason: String? = null,
)

@Serializable
data class SyncStatusOut(
    @SerialName("assessment_id") val assessmentId: Long,
    @SerialName("assessment_status") val assessmentStatus: String,
    @SerialName("revision_id") val revisionId: String? = null,
    @SerialName("manifest_state") val manifestState: String, // "none" | "received" | "complete" | "rejected"
    @SerialName("manifest_rejection_reason") val manifestRejectionReason: String? = null,
    val items: List<SyncItemStatusOut> = emptyList(),
    @SerialName("all_items_verified") val allItemsVerified: Boolean = false,
)

@Serializable
data class ApiErrorBody(
    val detail: String? = null,
)

// ---- P6 sync bootstrap (first-ever contact with the server for this device/assessment) ----

@Serializable
data class CandidateEnrollmentRequest(
    @SerialName("device_worker_id") val deviceWorkerId: String,
    @SerialName("enrollment_secret") val enrollmentSecret: String,
    @SerialName("client_assessment_id") val clientAssessmentId: String,
    @SerialName("full_name") val fullName: String,
    val phone: String,
    @SerialName("public_name_consent") val publicNameConsent: Boolean,
    @SerialName("consent_version") val consentVersion: String = "public-name-v1",
    @SerialName("qp_code") val qpCode: String,
    @SerialName("qp_version") val qpVersion: String,
)

@Serializable
data class WorkerRegisterRequest(
    @SerialName("device_worker_id") val deviceWorkerId: String,
    @SerialName("display_name") val displayName: String,
)

@Serializable
data class WorkerRegisterOut(
    @SerialName("worker_id") val workerId: Long,
)

@Serializable
data class PackLookupOut(
    @SerialName("pack_id") val packId: Long,
)

@Serializable
data class AssessmentCreateRequest(
    @SerialName("worker_id") val workerId: Long,
    @SerialName("pack_id") val packId: Long,
)

@Serializable
data class AssessmentCreatedOut(
    val id: Long,
    @SerialName("worker_token") val workerToken: String,
)

// ---- P7: task-specific reassessment requests + durable worker-updates polling ----

@Serializable
data class ReassessmentRequestOut(
    val id: Long,
    @SerialName("assessment_id") val assessmentId: Long,
    @SerialName("revision_number") val revisionNumber: Int,
    @SerialName("task_codes") val taskCodes: List<String>,
    val reason: String,
    @SerialName("capture_instructions") val captureInstructions: String,
    @SerialName("requested_by_id") val requestedById: Long,
    @SerialName("requested_at") val requestedAt: String,
    val status: String, // "pending" | "fulfilled" | "cancelled"
)

@Serializable
data class AssessmentRevisionOut(
    @SerialName("revision_number") val revisionNumber: Int,
    @SerialName("revision_id") val revisionId: String? = null,
    @SerialName("reopened_task_codes") val reopenedTaskCodes: List<String>? = null,
    val status: String,
    @SerialName("created_at") val createdAt: String,
    @SerialName("submitted_at") val submittedAt: String? = null,
)

@Serializable
data class WorkerUpdatesOut(
    @SerialName("assessment_id") val assessmentId: Long,
    @SerialName("assessment_status") val assessmentStatus: String,
    @SerialName("revision_number") val revisionNumber: Int,
    @SerialName("pending_reassessment_request") val pendingReassessmentRequest: ReassessmentRequestOut? = null,
    @SerialName("report_status") val reportStatus: String, // "none" | "pending" | "available"
    @SerialName("latest_event_id") val latestEventId: Long,
)
