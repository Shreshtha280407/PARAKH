package `in`.kaushalpramaan.core.seal

import java.security.KeyPairGenerator
import java.security.spec.ECGenParameterSpec
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * [ManifestSigner.sign]/[ManifestSigner.verify] are pure JCE Signature operations once handed
 * a key -- testable with any EC key pair, not only a real Android Keystore one (which
 * [ManifestSigner.getOrCreateSigningKey] requires a real device for; see
 * ManifestSignerInstrumentedTest). A software EC key here exercises the exact same signing
 * algorithm and verification logic the production Keystore-backed key will use.
 */
class ManifestSignerTest {

    private fun generateSoftwareEcKeyPair() =
        KeyPairGenerator.getInstance("EC").apply { initialize(ECGenParameterSpec("secp256r1")) }.generateKeyPair()

    @Test
    fun an_untouched_manifest_and_signature_verify_successfully() {
        val keyPair = generateSoftwareEcKeyPair()
        val data = "canonical manifest bytes".encodeToByteArray()

        val signature = ManifestSigner.sign(data, keyPair.private)

        assertTrue(ManifestSigner.verify(data, signature, keyPair.public))
    }

    @Test
    fun verification_fails_after_a_one_byte_manifest_modification() {
        val keyPair = generateSoftwareEcKeyPair()
        val data = "canonical manifest bytes".encodeToByteArray()
        val signature = ManifestSigner.sign(data, keyPair.private)

        val tampered = data.copyOf().also { it[0] = (it[0] + 1).toByte() }

        assertFalse(ManifestSigner.verify(tampered, signature, keyPair.public))
    }

    @Test
    fun verification_fails_after_a_one_byte_signature_modification() {
        val keyPair = generateSoftwareEcKeyPair()
        val data = "canonical manifest bytes".encodeToByteArray()
        val signature = ManifestSigner.sign(data, keyPair.private)

        val tamperedSignature = signature.copyOf().also { it[0] = (it[0] + 1).toByte() }

        assertFalse(ManifestSigner.verify(data, tamperedSignature, keyPair.public))
    }

    @Test
    fun verification_fails_against_the_wrong_public_key() {
        val keyPair = generateSoftwareEcKeyPair()
        val wrongKeyPair = generateSoftwareEcKeyPair()
        val data = "canonical manifest bytes".encodeToByteArray()
        val signature = ManifestSigner.sign(data, keyPair.private)

        assertFalse(ManifestSigner.verify(data, signature, wrongKeyPair.public))
    }

    @Test
    fun verify_never_throws_on_garbage_signature_bytes() {
        val keyPair = generateSoftwareEcKeyPair()
        val data = "canonical manifest bytes".encodeToByteArray()
        assertFalse(ManifestSigner.verify(data, byteArrayOf(1, 2, 3), keyPair.public))
    }
}
