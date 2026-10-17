package `in`.kaushalpramaan.app.data

import android.content.Context
import android.util.Base64
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import org.json.JSONObject
import java.security.SecureRandom
import java.util.UUID

/** Local profile and PIN verifier survive onboarding interruptions before Room's
 * assessment exists. No raw PIN is stored. Backup is disabled in the manifest. */
@Suppress("DEPRECATION")
class CandidateSecurity(context: Context) {
    private val prefs = EncryptedSharedPreferences.create(context, "kp_candidate_security",
        MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM)
    fun configured(): Boolean = prefs.contains("verifier")
    fun profile(): WorkerRegistration? = prefs.getString("profile", null)?.let {
        val data = JSONObject(it)
        WorkerRegistration(data.getString("workerId"), data.getString("phone"),
            data.getString("fullName"), data.getBoolean("publicNameConsent"), data.getString("enrollmentSecret"))
    }
    @Synchronized fun register(name: String, phone: String, consent: Boolean, pin: CharArray): WorkerRegistration {
        check(!configured()) { "Unlock the existing profile before replacing it" }
        val salt = PinVerifier.salt()
        val verifier = PinVerifier.derive(pin, salt)
        val secret = ByteArray(32).also { SecureRandom().nextBytes(it) }.joinToString("") { "%02x".format(it) }
        val profile = WorkerRegistration("KP-" + UUID.randomUUID(), phone, name, consent, secret)
        check(prefs.edit().putString("salt", encode(salt)).putString("verifier", encode(verifier))
            .putString("profile", JSONObject().put("workerId", profile.workerId).put("phone", phone)
                .put("fullName", name).put("publicNameConsent", consent).put("enrollmentSecret", secret).toString())
            .putInt("failures", 0).putLong("lockedUntil", 0).commit())
        return profile
    }
    @Synchronized fun setLegacyPin(pin: CharArray) {
        check(!configured())
        val salt = PinVerifier.salt()
        check(prefs.edit().putString("salt", encode(salt)).putString("verifier", encode(PinVerifier.derive(pin, salt)))
            .putInt("failures", 0).putLong("lockedUntil", 0).commit())
    }
    fun remainingLockMillis(now: Long = System.currentTimeMillis()): Long =
        (prefs.getLong("lockedUntil", 0) - now).coerceAtLeast(0)
    @Synchronized fun unlock(pin: CharArray, now: Long = System.currentTimeMillis()): Boolean {
        if (!configured() || remainingLockMillis(now) > 0 || pin.size != 4 || pin.any { it !in '0'..'9' }) {
            pin.fill('\u0000'); return false
        }
        val valid = PinVerifier.matches(pin, decode(prefs.getString("salt", "")!!), decode(prefs.getString("verifier", "")!!))
        if (valid) prefs.edit().putInt("failures", 0).putLong("lockedUntil", 0).commit()
        else {
            val failures = prefs.getInt("failures", 0) + 1
            val delay = if (failures < 5) 0L else (30_000L * (1L shl (failures - 5).coerceAtMost(10))).coerceAtMost(86_400_000L)
            prefs.edit().putInt("failures", failures).putLong("lockedUntil", now + delay).commit()
        }
        return valid
    }
    @Synchronized fun clear() { check(prefs.edit().clear().commit()) }
    private fun encode(bytes: ByteArray) = Base64.encodeToString(bytes, Base64.NO_WRAP)
    private fun decode(value: String) = Base64.decode(value, Base64.NO_WRAP)
}
