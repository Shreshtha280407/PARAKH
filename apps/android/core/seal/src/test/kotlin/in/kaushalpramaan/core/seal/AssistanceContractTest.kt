package `in`.kaushalpramaan.core.seal

import java.io.File
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class AssistanceContractTest {
    private val json = SealManifest.CANONICAL_JSON
    private val root = generateSequence(File(System.getProperty("user.dir"))) { it.parentFile }
        .first { File(it, "contracts/fixtures").isDirectory }
    private fun fixture(name: String) = json.decodeFromString<AssistanceSnapshot>(File(root, "contracts/fixtures/assistance-v1-$name.json").readText())

    @Test fun shared_python_schema_fixtures_roundtrip_with_exact_field_names_and_defaults() {
        for (name in listOf("photo", "video", "pending")) {
            val text = File(root, "contracts/fixtures/assistance-v1-$name.json").readText()
            assertEquals(json.parseToJsonElement(text), json.parseToJsonElement(json.encodeToString(AssistanceSnapshot.serializer(), fixture(name))))
        }
    }
    @Test fun boundaries_and_revisions_are_bound_to_exact_media() {
        val s = fixture("video")
        assertEquals(5000L, s.flags.last().endMs)
        s.validateBinding(s.assessmentId, s.taskId, s.evidenceId, s.mediaSha256, 5000)
        assertThrows(IllegalArgumentException::class.java) { s.validateBinding(s.assessmentId, s.taskId, "replacement", s.mediaSha256, 5000) }
        assertThrows(IllegalArgumentException::class.java) { s.copy(flags = listOf(s.flags.last().copy(endMs = 5001))) }
        assertThrows(IllegalArgumentException::class.java) { s.copy(flags = listOf(s.flags.last().copy(startMs = 5000))) }
        assertThrows(IllegalArgumentException::class.java) { s.copy(status = AssistanceStatus.QUEUED) }
    }
    @Test fun numeric_future_version_and_oversize_data_are_rejected() {
        assertThrows(IllegalArgumentException::class.java) { fixture("video").copy(contractVersion = 2) }
        assertThrows(IllegalArgumentException::class.java) { AssistanceFlag(AssistanceFlagType.DARK, observed = Double.NaN) }
        assertThrows(IllegalArgumentException::class.java) { AssistanceFlag(AssistanceFlagType.DARK, threshold = Double.POSITIVE_INFINITY) }
        assertThrows(IllegalArgumentException::class.java) { AssistanceFlag(AssistanceFlagType.DARK, 1_200_000, 1_200_001) }
        assertThrows(IllegalArgumentException::class.java) { fixture("video").copy(flags = List(257) { fixture("video").flags.first() }) }
        assertThrows(IllegalArgumentException::class.java) { fixture("photo").copy(hands = fixture("video").hands) }
        assertThrows(IllegalArgumentException::class.java) { fixture("video").copy(intervalsTruncated = true) }
        val unsupported = fixture("pending").copy(durationMs = 1_200_001, status = AssistanceStatus.UNAVAILABLE, errorCategory = AssistanceError.MODEL_UNAVAILABLE)
        assertEquals(1_200_001L, unsupported.durationMs)
    }
    @Test fun legacy_items_omit_new_null_field_and_new_snapshots_are_in_signed_bytes() {
        val item = ManifestEvidenceItem("id", "T1", "PHOTO", "photo.jpg", 100, "b".repeat(64), "image/jpeg", processing = "FITS_AS_IS")
        val legacy = json.encodeToString(ManifestEvidenceItem.serializer(), item)
        assertFalse(legacy.contains("assistance"))
        val newItem = item.copy(assistance = fixture("photo"))
        val signed = json.encodeToString(ManifestEvidenceItem.serializer(), newItem)
        assertTrue(signed.contains("\"assistance\""))
        assertNotEquals(signed, json.encodeToString(ManifestEvidenceItem.serializer(), newItem.copy(assistance = fixture("photo").copy(flags = emptyList()))))
    }
    @Test fun metadata_budget_drops_new_diagnostics_honestly_without_changing_inherited_evidence() {
        val snapshot = fixture("video")
        val verbose = snapshot.copy(flags = (0 until 200).map {
            AssistanceFlag(AssistanceFlagType.DARK, it * 10L, it * 10L + 5)
        })
        val base = ManifestEvidenceItem(snapshot.evidenceId, "T1", "VIDEO", "video.mp4", 100,
            snapshot.mediaSha256, "video/mp4", 5000, processing = "FITS_AS_IS", assistance = verbose)
        val inherited = base.copy(evidenceId = "inherited", processing = "INHERITED", assistance = snapshot.copy(evidenceId = "inherited"))
        val manifest = SealManifest(2, snapshot.assessmentId, snapshot.revisionId, "CON/Q0602", "4.0", "test", 1, 2,
            true, 2, listOf(base, inherited), listOf(ManifestTaskTotal("T1", 200, 15_728_640)), 200, 125_829_120,
            "key", "signer", "pub")
        val compact = manifest.withBoundedAssistance(6000)
        assertTrue(compact.canonicalJsonBytes().size <= 6000)
        assertEquals(AssistanceStatus.UNAVAILABLE, compact.evidence.first().assistance!!.status)
        assertEquals(AssistanceError.PAYLOAD_LIMIT, compact.evidence.first().assistance!!.errorCategory)
        assertEquals(base.sha256, compact.evidence.first().sha256)
        assertEquals(base.bytes, compact.evidence.first().bytes)
        assertEquals(inherited, compact.evidence.last())
    }
}
