package `in`.kaushalpramaan.app.data.sync

import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

private class FixedEndpoint(private val url: String) : SyncEndpointConfig {
    override fun baseUrl(): String = url
    override fun supportsRuntimeOverride(): Boolean = true
    override fun setOverrideBaseUrl(url: String?) { /* unused in these tests */ }
}

/**
 * Pure HTTP-layer tests for [SyncApiClient]/[SyncBootstrapClient] against a real local
 * [MockWebServer] -- no Android framework, no crypto, no Room; just proves every call shape
 * (method/path/headers/body) and every error-category mapping are correct. The security-
 * critical streaming-decrypt/Room/real-device paths are covered separately by
 * SyncRepositoryInstrumentedTest (real device required -- see docs/gates/P6.md).
 */
class SyncApiClientTest {
    private lateinit var server: MockWebServer
    private lateinit var client: SyncApiClient
    private lateinit var bootstrap: SyncBootstrapClient

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        val endpoint = FixedEndpoint(server.url("/").toString().removeSuffix("/"))
        client = SyncApiClient(endpoint, "test-worker-token")
        bootstrap = SyncBootstrapClient(endpoint)
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun open_manifest_session_sends_the_expected_body_and_header_and_parses_the_response() {
        server.enqueue(
            MockResponse().setResponseCode(201).setBody(
                """{"id":1,"assessment_id":42,"assessment_task_id":null,"target":"manifest","kind":null,"mime":null,"claimed_size_bytes":100,"received_bytes":0,"next_chunk_index":0,"status":"open","revision_id":"rev-1","client_evidence_id":null}""",
            ),
        )
        val out = client.openOrRecoverManifestSession(42, "rev-1", 100)
        assertEquals(1, out.id)
        assertEquals("open", out.status)

        val recorded = server.takeRequest()
        assertEquals("POST", recorded.method)
        assertEquals("/uploads", recorded.path)
        assertEquals("test-worker-token", recorded.getHeader("X-Worker-Token"))
        assertTrue(recorded.body.readUtf8().contains("\"target\":\"manifest\""))
    }

    @Test
    fun put_chunk_sends_raw_bytes_as_the_body_with_octet_stream_content_type() {
        server.enqueue(MockResponse().setBody("""{"chunk_index":0,"received_bytes":5,"next_chunk_index":1,"status":"open"}"""))
        val chunk = byteArrayOf(1, 2, 3, 4, 5)
        val ack = client.putChunk(7, 0, chunk)
        assertEquals(5L, ack.receivedBytes)

        val recorded = server.takeRequest()
        assertEquals("PUT", recorded.method)
        assertEquals("/uploads/7/chunks/0", recorded.path)
        assertEquals("application/octet-stream", recorded.getHeader("Content-Type"))
        assertEquals(5, recorded.bodySize.toInt())
    }

    @Test
    fun a_409_hash_mismatch_is_categorised_as_integrity_rejected() {
        server.enqueue(MockResponse().setResponseCode(409).setBody("""{"detail":"hash mismatch: server computed aaa, client declared bbb"}"""))
        val e = assertThrows(SyncApiException::class.java) { client.completeEvidence(1, "a".repeat(64)) }
        assertEquals(SyncErrorCategory.INTEGRITY_REJECTED, e.category)
        assertEquals(409, e.httpCode)
    }

    @Test
    fun a_409_revision_superseded_is_categorised_as_non_retryable_revision_superseded() {
        server.enqueue(MockResponse().setResponseCode(409).setBody("""{"detail":"revision 'rev-OLD' has been superseded by 'rev-NEW'; abandon this upload"}"""))
        val e = assertThrows(SyncApiException::class.java) { client.getSessionStatus(1) }
        assertEquals(SyncErrorCategory.REVISION_SUPERSEDED, e.category)
        assertTrue(!e.category.retryable)
    }

    @Test
    fun a_409_manifest_rejected_signature_is_categorised_as_non_retryable_signature_rejected() {
        server.enqueue(MockResponse().setResponseCode(409).setBody("""{"detail":"manifest rejected: ECDSA signature does not verify against the embedded public key"}"""))
        val e = assertThrows(SyncApiException::class.java) { client.completeManifest(1, "a".repeat(64)) }
        assertEquals(SyncErrorCategory.SIGNATURE_REJECTED, e.category)
        assertTrue(!e.category.retryable)
    }

    @Test
    fun a_401_is_categorised_as_non_retryable_unauthorized() {
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"detail":"missing or invalid X-Worker-Token"}"""))
        val e = assertThrows(SyncApiException::class.java) { client.getSyncStatus(1, null) }
        assertEquals(SyncErrorCategory.UNAUTHORIZED, e.category)
        assertTrue(!e.category.retryable)
    }

    @Test
    fun a_500_is_categorised_as_retryable_server_unavailable() {
        server.enqueue(MockResponse().setResponseCode(500).setBody("""{"detail":"internal error"}"""))
        val e = assertThrows(SyncApiException::class.java) { client.submitAssessment(1) }
        assertEquals(SyncErrorCategory.SERVER_UNAVAILABLE, e.category)
        assertTrue(e.category.retryable)
    }

    @Test
    fun a_dropped_connection_is_categorised_as_retryable_network_unavailable() {
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_START))
        val e = assertThrows(SyncApiException::class.java) { client.getSessionStatus(1) }
        assertEquals(SyncErrorCategory.NETWORK_UNAVAILABLE, e.category)
        assertTrue(e.category.retryable)
    }

    @Test
    fun worker_register_sends_no_worker_token_header_pre_auth() {
        server.enqueue(MockResponse().setBody("""{"worker_id":5}"""))
        val id = bootstrap.registerWorker("KP-ABCDEF01", "Worker")
        assertEquals(5L, id)
        val recorded = server.takeRequest()
        assertNull(recorded.getHeader("X-Worker-Token"))
        assertTrue(recorded.body.readUtf8().contains("KP-ABCDEF01"))
    }

    @Test
    fun resolve_pack_id_url_encodes_the_qp_code_query_parameter() {
        server.enqueue(MockResponse().setBody("""{"pack_id":3,"qp_code":"CON/Q0602","qp_version":"v4.0"}"""))
        val id = bootstrap.resolvePackId("CON/Q0602", "v4.0")
        assertEquals(3L, id)
        val recorded = server.takeRequest()
        assertTrue(recorded.path!!.contains("qp_code=CON%2FQ0602"))
    }

    @Test
    fun create_assessment_returns_the_id_and_the_one_time_worker_token() {
        server.enqueue(MockResponse().setResponseCode(201).setBody("""{"id":99,"worker_token":"raw-token-value"}"""))
        val (id, token) = bootstrap.createAssessment(workerId = 5, packId = 3)
        assertEquals(99L, id)
        assertEquals("raw-token-value", token)
    }
}
