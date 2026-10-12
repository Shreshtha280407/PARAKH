package `in`.kaushalpramaan.core.seal

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Serializable
data class ManifestEvidenceItem(
    val evidenceId: String,
    val taskId: String,
    /** "PHOTO" | "VIDEO". */
    val kind: String,
    val fileName: String,
    val bytes: Long,
    val sha256: String,
    val mimeType: String,
    val durationMillis: Long? = null,
    val widthPx: Int? = null,
    val heightPx: Int? = null,
    /** e.g. "KEPT_AS_IS", "OPTIMIZED", "TRIMMED" -- how this final item was produced from its
     * raw capture, so a verifier/assessor can see at a glance whether anything was altered. */
    val processing: String,
)

@Serializable
data class ManifestTaskTotal(val taskId: String, val finalBytes: Long, val budgetBytes: Long)

/**
 * The P5 canonical, tamper-evident manifest (spec part F). One instance describes everything
 * about a sealed package except the encrypted media bytes themselves. [canonicalJsonBytes]
 * deterministically serialises it (sorted collections, fixed declaration-order field layout,
 * compact UTF-8 JSON, no pretty-printing) so the exact same manifest content always produces
 * the exact same bytes to sign/hash/verify against, regardless of how the caller originally
 * assembled its evidence/task lists.
 */
@Serializable
data class SealManifest(
    val schemaVersion: Int,
    val assessmentId: String,
    val revisionId: String,
    val qpCode: String,
    /** Pinned QP version -- also stands in for the task-pack/rubric/mapping version
     * identifiers already used by the app (`core:mapping`'s `Rules`/`TasksFile` expose only
     * this one pack-version identifier; P5 does not invent additional version fields the rest
     * of the app has no source of truth for). */
    val qpVersion: String,
    val appVersion: String,
    val createdAtMillis: Long,
    val sealedAtMillis: Long,
    val attestationConfirmed: Boolean,
    val attestationAtMillis: Long,
    val evidence: List<ManifestEvidenceItem>,
    val taskTotals: List<ManifestTaskTotal>,
    val assessmentFinalBytes: Long,
    val assessmentBudgetBytes: Long,
    /** Stable across re-seals of the same revision -- P6's future upload idempotency key. */
    val idempotencyKey: String,
    val signerKeyId: String,
    val signerPublicKeyBase64: String,
) {
    /** Deterministic canonical form: evidence/taskTotals sorted by their own id so caller
     * list-construction order never affects the signed bytes, encoded as compact
     * (no-whitespace) UTF-8 JSON in this class's fixed declaration order. */
    fun canonicalJsonBytes(): ByteArray {
        val canonical = copy(
            evidence = evidence.sortedBy { it.evidenceId },
            taskTotals = taskTotals.sortedBy { it.taskId },
        )
        return CANONICAL_JSON.encodeToString(serializer(), canonical).encodeToByteArray()
    }

    companion object {
        val CANONICAL_JSON = Json {
            prettyPrint = false
            encodeDefaults = true
            explicitNulls = true
        }
    }
}

/** The one small plaintext envelope actually written to the vault's manifest slot: the
 * canonical manifest bytes (base64, so this whole envelope is itself trivially re-serialised
 * as JSON) plus its detached signature and algorithm. [SealManifest.canonicalJsonBytes] is
 * always the exact bytes [manifestBase64] decodes to -- verification re-decodes
 * [manifestBase64] and checks [signatureBase64] against those exact bytes, never against this
 * envelope's own serialised form (which is not canonicalised/signed itself). */
@Serializable
data class SignedManifestPackage(
    val manifestBase64: String,
    val signatureBase64: String,
    val algorithm: String,
    val signerKeyId: String,
    val signerPublicKeyBase64: String,
) {
    fun toJsonBytes(): ByteArray = SealManifest.CANONICAL_JSON.encodeToString(serializer(), this).encodeToByteArray()

    companion object {
        fun fromJsonBytes(bytes: ByteArray): SignedManifestPackage =
            SealManifest.CANONICAL_JSON.decodeFromString(serializer(), bytes.decodeToString())
    }
}
