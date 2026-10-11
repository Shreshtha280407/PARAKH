package `in`.kaushalpramaan.app.data.draft

import android.content.Context
import android.util.Base64
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import androidx.sqlite.db.SupportSQLiteDatabase
import java.security.SecureRandom
import net.sqlcipher.database.SQLiteDatabase
import net.sqlcipher.database.SupportFactory

/** P4 closure: adds `debug_ceiling_requested` to `evidence_drafts` so the fail-closed
 * final-size check at finalizeCapture() can recompute the exact ceiling that was active
 * for a given capture (see EvidenceRepository). A real, additive migration -- never
 * fallbackToDestructiveMigration -- since existing drafts (even P4_TEST_ONLY ones) must
 * never be silently wiped by a schema change. */
val MIGRATION_1_2 = object : Migration(1, 2) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE evidence_drafts ADD COLUMN debug_ceiling_requested INTEGER NOT NULL DEFAULT 0")
    }
}

@androidx.room.Database(
    entities = [AssessmentDraftEntity::class, TaskDraftEntity::class, EvidenceDraftEntity::class],
    version = 2,
    exportSchema = true,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun assessmentDraftDao(): AssessmentDraftDao
    abstract fun taskDraftDao(): TaskDraftDao
    abstract fun evidenceDraftDao(): EvidenceDraftDao

    companion object {
        private const val DB_FILE_NAME = "kp_drafts.db"

        @Volatile private var instance: AppDatabase? = null

        fun getInstance(context: Context): AppDatabase =
            instance ?: synchronized(this) {
                instance ?: build(context.applicationContext, DB_FILE_NAME).also { instance = it }
            }

        /** Test-only: closes and drops the cached singleton so the next [getInstance] call
         * rebuilds fresh against whatever is on disk at that point. Instrumented tests
         * normally share one app process across every @Test method/class in the same run,
         * so deleting the database file on disk between tests has no effect on an
         * already-cached, already-open connection without this. */
        internal fun resetInstanceForTesting() {
            synchronized(this) {
                instance?.close()
                instance = null
            }
        }

        /** Internal (not private) purely so an instrumented test can build an isolated,
         * non-singleton instance against a chosen file name to prove the real SQLCipher
         * wiring end to end without disturbing [getInstance]'s process-wide cached instance
         * that the rest of the running app may already hold open. Production code must
         * always go through [getInstance]. */
        internal fun build(appContext: Context, dbFileName: String): AppDatabase {
            SQLiteDatabase.loadLibs(appContext)
            val passphrase = DatabaseKeyProvider(appContext).getOrCreatePassphrase()
            val factory = SupportFactory(passphrase)
            return Room.databaseBuilder(appContext, AppDatabase::class.java, dbFileName)
                .openHelperFactory(factory)
                .addMigrations(MIGRATION_1_2)
                .build()
        }
    }
}

/**
 * Produces the SQLCipher passphrase for [AppDatabase] without ever holding, logging, or
 * persisting it as plaintext. The passphrase itself is 32 cryptographically random bytes
 * (not a human secret), stored on disk only in its AES-256-GCM-encrypted form via
 * [EncryptedSharedPreferences], whose own encryption key ([MasterKey]) is generated inside
 * and never leaves the Android Keystore (hardware-backed where available) -- it cannot be
 * exported, dumped, or read back as raw key material by this or any other app. Losing
 * Keystore access (e.g. a factory reset) makes the encrypted passphrase permanently
 * unreadable, which is the correct, intended failure mode for on-device-only draft data.
 */
class DatabaseKeyProvider(private val context: Context) {

    fun getOrCreatePassphrase(): ByteArray {
        val prefs = encryptedPrefs()
        val existing = prefs.getString(KEY_ALIAS, null)
        if (existing != null) {
            return Base64.decode(existing, Base64.NO_WRAP)
        }
        val fresh = ByteArray(PASSPHRASE_BYTES)
        SecureRandom().nextBytes(fresh)
        prefs.edit().putString(KEY_ALIAS, Base64.encodeToString(fresh, Base64.NO_WRAP)).apply()
        return fresh
    }

    // MasterKey/EncryptedSharedPreferences are marked deprecated in security-crypto 1.1.0
    // with no stable (non-alpha) replacement published yet; this is still the officially
    // supported stable API for Keystore-backed encrypted prefs, so it is used deliberately
    // rather than depending on an unstable alpha API in production code.
    @Suppress("DEPRECATION")
    private fun encryptedPrefs() = run {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            PREFS_FILE_NAME,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    companion object {
        private const val PREFS_FILE_NAME = "kp_db_key_store"
        private const val KEY_ALIAS = "db_passphrase_v1"
        private const val PASSPHRASE_BYTES = 32
    }
}
