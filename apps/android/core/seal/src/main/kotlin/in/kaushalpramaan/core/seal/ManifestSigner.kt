package `in`.kaushalpramaan.core.seal

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyStore
import java.security.PrivateKey
import java.security.PublicKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec

/**
 * Canonical-manifest signing (P5 spec part F). [getOrCreateSigningKey] generates a
 * non-exportable EC signing key directly inside the Android Keystore -- the private key
 * material never leaves it, is never readable by this or any other app, and [sign] only ever
 * receives a [KeyStore.PrivateKeyEntry] handle, never raw key bytes. [verify] is pure
 * cryptographic verification against any EC [PublicKey] (Keystore-backed in production, a
 * software key in tests) -- independently testable off a real device.
 */
object ManifestSigner {
    const val SIGNATURE_ALGORITHM = "SHA256withECDSA"
    private const val ANDROID_KEYSTORE = "AndroidKeyStore"
    private const val EC_CURVE = "secp256r1"

    /** Returns the existing signing key for [keyAlias], generating a fresh one inside the
     * Android Keystore if none exists yet. Idempotent -- safe to call on every seal. */
    fun getOrCreateSigningKey(keyAlias: String): KeyStore.PrivateKeyEntry {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (keyStore.getEntry(keyAlias, null) as? KeyStore.PrivateKeyEntry)?.let { return it }

        val generator = java.security.KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, ANDROID_KEYSTORE)
        generator.initialize(
            KeyGenParameterSpec.Builder(keyAlias, KeyProperties.PURPOSE_SIGN)
                .setDigests(KeyProperties.DIGEST_SHA256)
                .setAlgorithmParameterSpec(ECGenParameterSpec(EC_CURVE))
                .build(),
        )
        generator.generateKeyPair()
        return keyStore.getEntry(keyAlias, null) as KeyStore.PrivateKeyEntry
    }

    fun sign(canonicalBytes: ByteArray, privateKey: PrivateKey): ByteArray {
        val signature = Signature.getInstance(SIGNATURE_ALGORITHM)
        signature.initSign(privateKey)
        signature.update(canonicalBytes)
        return signature.sign()
    }

    /** True iff [signatureBytes] is a valid [SIGNATURE_ALGORITHM] signature of exactly
     * [canonicalBytes] under [publicKey]. Never throws -- a malformed signature is simply not
     * valid, not an error. */
    fun verify(canonicalBytes: ByteArray, signatureBytes: ByteArray, publicKey: PublicKey): Boolean = try {
        val signature = Signature.getInstance(SIGNATURE_ALGORITHM)
        signature.initVerify(publicKey)
        signature.update(canonicalBytes)
        signature.verify(signatureBytes)
    } catch (_: Exception) {
        false
    }
}
