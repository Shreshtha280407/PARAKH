package `in`.kaushalpramaan.app.data

import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec

/** CPU-hardened verifier; the containing record is additionally Keystore encrypted.
 * Four digits never authorize cloud requests. Keep this work off the UI thread. */
object PinVerifier {
    const val ITERATIONS = 600_000
    fun salt(): ByteArray = ByteArray(32).also { SecureRandom().nextBytes(it) }
    fun derive(pin: CharArray, salt: ByteArray): ByteArray {
        require(pin.size == 4 && pin.all { it in '0'..'9' })
        val spec = PBEKeySpec(pin, salt, ITERATIONS, 256)
        return try { SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).encoded }
        finally { spec.clearPassword(); pin.fill('\u0000') }
    }
    fun matches(pin: CharArray, salt: ByteArray, expected: ByteArray): Boolean =
        MessageDigest.isEqual(derive(pin, salt), expected)
}
