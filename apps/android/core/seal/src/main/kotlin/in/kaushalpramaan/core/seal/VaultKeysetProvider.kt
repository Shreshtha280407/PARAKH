package `in`.kaushalpramaan.core.seal

import android.content.Context
import com.google.crypto.tink.StreamingAead
import com.google.crypto.tink.integration.android.AndroidKeysetManager
import com.google.crypto.tink.streamingaead.StreamingAeadConfig
import com.google.crypto.tink.streamingaead.StreamingAeadKeyTemplates

/**
 * The one production source of the P5 vault's [StreamingAead] primitive. The Tink keyset
 * itself is protected by an Android Keystore-backed master key via [AndroidKeysetManager] --
 * Tink's own recommended production pattern -- so the keyset material on disk
 * (SharedPreferences) is only ever the Keystore-wrapped, encrypted form; the raw key is never
 * held, logged, or exportable. [VaultStreamCipher] does the actual per-file encrypt/decrypt
 * once it has this primitive.
 */
class VaultKeysetProvider(private val context: Context) {

    /** The one production entry point other modules (`:app`) use -- returns a [VaultCipher],
     * never the raw Tink [StreamingAead] type, so Tink stays an implementation detail fully
     * encapsulated inside this module (callers never need a Tink dependency of their own). */
    fun getOrCreateCipher(): VaultCipher = VaultCipher(getOrCreateStreamingAead())

    // StreamingAeadKeyTemplates/getPrimitive(Class) are marked deprecated in Tink 1.23 in
    // favor of a newer Parameters-based builder API, with no published stable replacement for
    // AndroidKeysetManager's own Keystore-backed workflow yet -- the same situation as (and
    // following the same deliberate-use-of-the-still-supported-API precedent already set by)
    // DatabaseKeyProvider's MasterKey/EncryptedSharedPreferences usage for P4.
    @Suppress("DEPRECATION")
    internal fun getOrCreateStreamingAead(): StreamingAead {
        StreamingAeadConfig.register()
        val manager = AndroidKeysetManager.Builder()
            .withSharedPref(context, KEYSET_NAME, PREFS_FILE_NAME)
            .withKeyTemplate(StreamingAeadKeyTemplates.AES256_GCM_HKDF_4KB)
            .withMasterKeyUri(ANDROID_KEYSTORE_URI_PREFIX + MASTER_KEY_ALIAS)
            .build()
        return manager.keysetHandle.getPrimitive(StreamingAead::class.java)
    }

    companion object {
        private const val KEYSET_NAME = "kp_vault_keyset"
        private const val PREFS_FILE_NAME = "kp_vault_keyset_prefs"
        private const val MASTER_KEY_ALIAS = "kp_vault_master_key"
        private const val ANDROID_KEYSTORE_URI_PREFIX = "android-keystore://"
    }
}
