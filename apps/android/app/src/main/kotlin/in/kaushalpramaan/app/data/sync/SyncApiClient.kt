package `in`.kaushalpramaan.app.data.sync

import java.io.IOException
import java.net.SocketTimeoutException
import kotlinx.serialization.SerializationException
import kotlinx.serialization.encodeToString
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response

private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
private val OCTET_STREAM_MEDIA_TYPE = "application/octet-stream".toMediaType()

/** Thrown for every sync HTTP failure -- never a raw [IOException]/[SerializationException]
 * escapes [SyncApiClient], so callers (SyncRepository) always get one safe, categorised type
 * to branch on. [message] is kept for in-memory control flow / developer Logcat only (never
 * written to Room -- see OutboxItemEntity.lastErrorCategory's own doc comment) and never
 * contains a capability token, file path, or plaintext evidence content; the server's own
 * error bodies never echo any of those back either. */
class SyncApiException(
    val category: SyncErrorCategory,
    val httpCode: Int? = null,
    message: String? = null,
) : Exception(message)

/**
 * Thin, real HTTP client for the P6 server API (server/app/routers/uploads.py,
 * routers/assessments.py) -- see SyncModels.kt for the exact wire shapes. One instance per
 * worker-token (i.e. per assessment); stateless beyond that. Every call maps a failure to a
 * [SyncApiException] with a [SyncErrorCategory] -- never leaks a raw OkHttp/IO exception.
 */
class SyncApiClient(
    private val endpointConfig: SyncEndpointConfig,
    private val workerToken: String,
) {
    private val base: String get() = endpointConfig.baseUrl().trimEnd('/')
    private val json = SyncHttpClient.json
    private val client = SyncHttpClient.client

    private fun requestBuilder(path: String): Request.Builder =
        Request.Builder().url("$base$path").header("X-Worker-Token", workerToken)

    private inline fun <reified T> execute(request: Request, expectCode: Int = 200): T {
        val response: Response = try {
            client.newCall(request).execute()
        } catch (e: SocketTimeoutException) {
            throw SyncApiException(SyncErrorCategory.TIMEOUT, message = "request timed out")
        } catch (e: IOException) {
            throw SyncApiException(SyncErrorCategory.NETWORK_UNAVAILABLE, message = "network unavailable")
        }
        response.use {
            val bodyText = it.body?.string().orEmpty()
            if (it.code != expectCode) {
                throw SyncApiException(categoryFor(it.code, bodyText), it.code, extractDetail(bodyText))
            }
            return try {
                json.decodeFromString(bodyText)
            } catch (e: SerializationException) {
                throw SyncApiException(SyncErrorCategory.UNKNOWN_SERVER_ERROR, it.code, "unparseable response body")
            }
        }
    }

    private fun executeNoBody(request: Request, expectCode: Int = 200) {
        val response: Response = try {
            client.newCall(request).execute()
        } catch (e: SocketTimeoutException) {
            throw SyncApiException(SyncErrorCategory.TIMEOUT, message = "request timed out")
        } catch (e: IOException) {
            throw SyncApiException(SyncErrorCategory.NETWORK_UNAVAILABLE, message = "network unavailable")
        }
        response.use {
            if (it.code != expectCode) {
                val bodyText = it.body?.string().orEmpty()
                throw SyncApiException(categoryFor(it.code, bodyText), it.code, extractDetail(bodyText))
            }
        }
    }

    private fun extractDetail(bodyText: String): String? =
        try {
            json.decodeFromString<ApiErrorBody>(bodyText).detail
        } catch (e: SerializationException) {
            null
        }

    private fun categoryFor(httpCode: Int, bodyText: String): SyncErrorCategory {
        val detail = extractDetail(bodyText).orEmpty().lowercase()
        return when {
            httpCode == 401 || httpCode == 403 -> SyncErrorCategory.UNAUTHORIZED
            httpCode == 409 && "superseded" in detail -> SyncErrorCategory.REVISION_SUPERSEDED
            httpCode == 409 && ("quota" in detail || "budget" in detail) -> SyncErrorCategory.QUOTA_EXCEEDED
            httpCode == 409 && "signature" in detail -> SyncErrorCategory.SIGNATURE_REJECTED
            httpCode == 409 && ("hash" in detail || "does not match" in detail || "mismatch" in detail) ->
                SyncErrorCategory.INTEGRITY_REJECTED
            httpCode == 409 -> SyncErrorCategory.INTEGRITY_REJECTED
            httpCode in 500..599 -> SyncErrorCategory.SERVER_UNAVAILABLE
            else -> SyncErrorCategory.UNKNOWN_SERVER_ERROR
        }
    }

    /** Begin or recover an upload session for the manifest envelope. */
    fun openOrRecoverManifestSession(assessmentId: Long, revisionId: String, claimedSizeBytes: Long): UploadSessionOut {
        val body = json.encodeToString(
            UploadSessionCreateRequest(
                assessmentId = assessmentId, target = "manifest",
                claimedSizeBytes = claimedSizeBytes, revisionId = revisionId,
            ),
        )
        val request = requestBuilder("/uploads").post(body.toRequestBody(JSON_MEDIA_TYPE)).build()
        return execute(request, expectCode = 201)
    }

    /** Begin or recover an upload session for one evidence item. */
    fun openOrRecoverEvidenceSession(
        assessmentId: Long, taskCode: String, kind: String, mime: String, claimedSizeBytes: Long,
        revisionId: String, clientEvidenceId: String,
    ): UploadSessionOut {
        val body = json.encodeToString(
            UploadSessionCreateRequest(
                assessmentId = assessmentId, target = "evidence", taskCode = taskCode, kind = kind, mime = mime,
                claimedSizeBytes = claimedSizeBytes, revisionId = revisionId, clientEvidenceId = clientEvidenceId,
            ),
        )
        val request = requestBuilder("/uploads").post(body.toRequestBody(JSON_MEDIA_TYPE)).build()
        return execute(request, expectCode = 201)
    }

    /** Resume/status query -- "query per-item received-chunk status" before resuming. */
    fun getSessionStatus(sessionId: Long): UploadSessionOut {
        val request = requestBuilder("/uploads/$sessionId").get().build()
        return execute(request, expectCode = 200)
    }

    /** PUT exactly one <=1 MiB chunk. [chunkBytes] must already be the bounded, in-memory
     * chunk the caller read from the decrypting stream -- this function never reads from
     * disk/stream itself. */
    fun putChunk(sessionId: Long, chunkIndex: Int, chunkBytes: ByteArray): ChunkAck {
        val request = requestBuilder("/uploads/$sessionId/chunks/$chunkIndex")
            .put(chunkBytes.toRequestBody(OCTET_STREAM_MEDIA_TYPE))
            .build()
        return execute(request, expectCode = 200)
    }

    fun completeEvidence(sessionId: Long, sha256Hex: String): UploadReceipt {
        val body = json.encodeToString(UploadCompleteRequest(sha256Hex))
        val request = requestBuilder("/uploads/$sessionId/complete").post(body.toRequestBody(JSON_MEDIA_TYPE)).build()
        return execute(request, expectCode = 200)
    }

    fun completeManifest(sessionId: Long, sha256Hex: String): ManifestReceipt {
        val body = json.encodeToString(UploadCompleteRequest(sha256Hex))
        val request = requestBuilder("/uploads/$sessionId/complete").post(body.toRequestBody(JSON_MEDIA_TYPE)).build()
        return execute(request, expectCode = 200)
    }

    /** Resolve a possibly-lost acknowledgement via server status, and learn per-item progress,
     * before resuming or re-sending anything. */
    fun getSyncStatus(assessmentId: Long, revisionId: String?): SyncStatusOut {
        val path = if (revisionId != null) "/assessments/$assessmentId/sync-status?revision_id=$revisionId"
            else "/assessments/$assessmentId/sync-status"
        val request = requestBuilder(path).get().build()
        return execute(request, expectCode = 200)
    }

    /** Final step once every declared item is verified -- moves the assessment out of
     * 'draft' server-side (see routers/assessments.py::submit_assessment's P6 gate). Also
     * the P7 RESUBMIT path once a targeted-reassessment revision's manifest is complete
     * (same endpoint, same gate, now additionally accepted from 'needs_reassessment'). */
    fun submitAssessment(assessmentId: Long) {
        val request = requestBuilder("/assessments/$assessmentId/submit").post("".toRequestBody(null)).build()
        executeNoBody(request, expectCode = 200)
    }

    /** P7: durable, idempotent snapshot poll -- the latest pending reassessment request (if
     * any), current assessment status, and report availability. See
     * routers/reassessment.py::get_worker_updates. */
    fun getWorkerUpdates(assessmentId: Long, since: Long): WorkerUpdatesOut {
        val request = requestBuilder("/assessments/$assessmentId/worker-updates?since=$since").get().build()
        return execute(request, expectCode = 200)
    }

    /** v1/v2/... revision history -- same dual auth as GET /assessments/{id}. */
    fun getRevisions(assessmentId: Long): List<AssessmentRevisionOut> {
        val request = requestBuilder("/assessments/$assessmentId/revisions").get().build()
        return execute(request, expectCode = 200)
    }
}

/**
 * The three pre-auth bootstrap calls a phone makes the FIRST time it ever syncs a given
 * assessment draft -- none of these take (or need) a worker capability token, since none of
 * them exist yet at this point (see docs/gates/P6.md's "worker identity" design decision).
 * Kept as a separate class from [SyncApiClient] specifically so every other sync call's
 * "this requires a token" invariant is enforced by the type system, not by convention.
 */
class SyncBootstrapClient(private val endpointConfig: SyncEndpointConfig) {
    private val base: String get() = endpointConfig.baseUrl().trimEnd('/')
    private val json = SyncHttpClient.json
    private val client = SyncHttpClient.client

    private inline fun <reified T> execute(request: Request, expectCode: Int): T {
        val response: Response = try {
            client.newCall(request).execute()
        } catch (e: SocketTimeoutException) {
            throw SyncApiException(SyncErrorCategory.TIMEOUT, message = "request timed out")
        } catch (e: IOException) {
            throw SyncApiException(SyncErrorCategory.NETWORK_UNAVAILABLE, message = "network unavailable")
        }
        response.use {
            val bodyText = it.body?.string().orEmpty()
            if (it.code != expectCode) {
                val detail = try { json.decodeFromString<ApiErrorBody>(bodyText).detail } catch (e: SerializationException) { null }
                val category = when {
                    it.code in 500..599 -> SyncErrorCategory.SERVER_UNAVAILABLE
                    it.code == 404 -> SyncErrorCategory.UNKNOWN_SERVER_ERROR
                    else -> SyncErrorCategory.UNKNOWN_SERVER_ERROR
                }
                throw SyncApiException(category, it.code, detail)
            }
            return try {
                json.decodeFromString(bodyText)
            } catch (e: SerializationException) {
                throw SyncApiException(SyncErrorCategory.UNKNOWN_SERVER_ERROR, it.code, "unparseable response body")
            }
        }
    }

    /** Idempotent: the same [deviceWorkerId] always resolves to the same worker_id. */
    fun registerWorker(deviceWorkerId: String, displayName: String): Long {
        val body = json.encodeToString(WorkerRegisterRequest(deviceWorkerId, displayName))
        val request = Request.Builder().url("$base/workers/register")
            .post(body.toRequestBody(JSON_MEDIA_TYPE)).build()
        return execute<WorkerRegisterOut>(request, expectCode = 200).workerId
    }

    fun resolvePackId(qpCode: String, qpVersion: String): Long {
        val url = "$base/packs/by-code?qp_code=${qpCode.encodeUrlComponent()}&qp_version=${qpVersion.encodeUrlComponent()}"
        val request = Request.Builder().url(url).get().build()
        return execute<PackLookupOut>(request, expectCode = 200).packId
    }

    /** Returns (serverAssessmentId, workerToken). The token is returned exactly once, here --
     * see docs/worker_capability_tokens.md -- and must be persisted by the caller immediately. */
    fun createAssessment(workerId: Long, packId: Long): Pair<Long, String> {
        val body = json.encodeToString(AssessmentCreateRequest(workerId, packId))
        val request = Request.Builder().url("$base/assessments")
            .post(body.toRequestBody(JSON_MEDIA_TYPE)).build()
        val out = execute<AssessmentCreatedOut>(request, expectCode = 201)
        return out.id to out.workerToken
    }
}

private fun String.encodeUrlComponent(): String = java.net.URLEncoder.encode(this, "UTF-8")
