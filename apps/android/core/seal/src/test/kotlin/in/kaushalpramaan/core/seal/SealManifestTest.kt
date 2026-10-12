package `in`.kaushalpramaan.core.seal

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class SealManifestTest {

    private fun sampleManifest(evidenceOrder: List<String>, taskOrder: List<String>): SealManifest = SealManifest(
        schemaVersion = 1,
        assessmentId = "a1",
        revisionId = "r1",
        qpCode = "CON/Q0602",
        qpVersion = "v4.0",
        appVersion = "0.5.0-p5",
        createdAtMillis = 1_000L,
        sealedAtMillis = 2_000L,
        attestationConfirmed = true,
        attestationAtMillis = 1_500L,
        evidence = evidenceOrder.map { id ->
            ManifestEvidenceItem(
                evidenceId = id,
                taskId = "T1",
                kind = "PHOTO",
                fileName = "$id.jpg",
                bytes = 1000L,
                sha256 = "deadbeef",
                mimeType = "image/jpeg",
                processing = "KEPT_AS_IS",
            )
        },
        taskTotals = taskOrder.map { id -> ManifestTaskTotal(taskId = id, finalBytes = 1000L, budgetBytes = 15_000_000L) },
        assessmentFinalBytes = 1000L,
        assessmentBudgetBytes = 125_829_120L,
        idempotencyKey = "idem-1",
        signerKeyId = "key-1",
        signerPublicKeyBase64 = "base64pubkey",
    )

    @Test
    fun canonicalJsonBytes_is_identical_regardless_of_input_list_order() {
        val inOrder = sampleManifest(listOf("e1", "e2", "e3"), listOf("T1", "T2"))
        val reversed = sampleManifest(listOf("e3", "e2", "e1"), listOf("T2", "T1"))

        assertArrayEquals(
            "canonicalisation must sort collections by their own id, independent of caller order",
            inOrder.canonicalJsonBytes(),
            reversed.canonicalJsonBytes(),
        )
    }

    @Test
    fun canonicalJsonBytes_is_repeatable_for_the_exact_same_content() {
        val a = sampleManifest(listOf("e1", "e2"), listOf("T1"))
        val b = sampleManifest(listOf("e1", "e2"), listOf("T1"))
        assertArrayEquals(a.canonicalJsonBytes(), b.canonicalJsonBytes())
    }

    @Test
    fun canonicalJsonBytes_changes_when_any_real_field_changes() {
        val base = sampleManifest(listOf("e1"), listOf("T1"))
        val changed = base.copy(assessmentFinalBytes = base.assessmentFinalBytes + 1)
        assertFalse(base.canonicalJsonBytes().contentEquals(changed.canonicalJsonBytes()))
    }

    @Test
    fun canonicalJsonBytes_is_compact_utf8_with_no_pretty_printing() {
        val manifest = sampleManifest(listOf("e1"), listOf("T1"))
        val json = manifest.canonicalJsonBytes().decodeToString()
        assertFalse("canonical form must not contain pretty-print newlines", json.contains("\n"))
        assertFalse("canonical form must not contain pretty-print indentation", json.contains("  "))
    }
}
