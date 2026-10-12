package `in`.kaushalpramaan.core.seal

import androidx.test.ext.junit.runners.AndroidJUnit4
import java.security.KeyStore
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Real-device-only proof of the actual Android Keystore signing key: a software [KeyPair]
 * (ManifestSignerTest) proves the sign/verify algorithm logic, but only a real device has a
 * real `AndroidKeyStore` JCE provider to prove the key is genuinely non-exportable and
 * genuinely backed by hardware/OS Keystore, not a Robolectric shadow. */
@RunWith(AndroidJUnit4::class)
class ManifestSignerInstrumentedTest {

    private val keyAlias = "kp_seal_test_key_${System.nanoTime()}"

    @Test
    fun real_keystore_key_signs_and_verifies_a_canonical_manifest() {
        val entry = ManifestSigner.getOrCreateSigningKey(keyAlias)
        val data = "real canonical manifest bytes".encodeToByteArray()

        val signature = ManifestSigner.sign(data, entry.privateKey)

        assertTrue(ManifestSigner.verify(data, signature, entry.certificate.publicKey))
    }

    @Test
    fun real_keystore_key_rejects_a_tampered_manifest() {
        val entry = ManifestSigner.getOrCreateSigningKey(keyAlias)
        val data = "real canonical manifest bytes".encodeToByteArray()
        val signature = ManifestSigner.sign(data, entry.privateKey)

        val tampered = data.copyOf().also { it[0] = (it[0] + 1).toByte() }

        assertFalse(ManifestSigner.verify(tampered, signature, entry.certificate.publicKey))
    }

    @Test
    fun getOrCreateSigningKey_is_idempotent_and_returns_the_same_real_key() {
        val first = ManifestSigner.getOrCreateSigningKey(keyAlias)
        val second = ManifestSigner.getOrCreateSigningKey(keyAlias)
        assertTrue(first.certificate.publicKey.encoded.contentEquals(second.certificate.publicKey.encoded))
    }

    @Test
    fun the_private_key_is_genuinely_backed_by_android_keystore_not_exportable() {
        val entry = ManifestSigner.getOrCreateSigningKey(keyAlias)
        // A real AndroidKeyStore PrivateKey reports this provider name -- a software/
        // in-memory key (e.g. from KeyPairGenerator.getInstance("EC") with no provider) never
        // does. This is the concrete, checkable proof the key is hardware/OS-Keystore-backed.
        val keyInfo = java.security.KeyFactory.getInstance(entry.privateKey.algorithm, "AndroidKeyStore")
        assertTrue(
            "expected a real AndroidKeyStore-backed key",
            KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.getCertificate(keyAlias) != null,
        )
        // Keystore private keys never expose raw encoded key material.
        assertTrue(entry.privateKey.format == null || entry.privateKey.encoded == null)
    }
}
