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
import `in`.kaushalpramaan.app.data.assistance.AssistanceRecord
import `in`.kaushalpramaan.app.data.assistance.AssistanceDao

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

/** P5: adds the seal state machine columns to `assessment_drafts`, the per-item
 * optimisation-outcome columns to `evidence_drafts`, and the new `outbox_items` table -- real,
 * additive migration, never fallbackToDestructiveMigration, same reasoning as MIGRATION_1_2. */
val MIGRATION_2_3 = object : Migration(2, 3) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN seal_state TEXT NOT NULL DEFAULT 'DRAFT_EDITABLE'")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN revision_id TEXT")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN attestation_confirmed INTEGER NOT NULL DEFAULT 0")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN attestation_at_millis INTEGER")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN sealed_at_millis INTEGER")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN manifest_vault_relative_path TEXT")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN signer_key_id TEXT")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN signer_public_key_base64 TEXT")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN idempotency_key TEXT")

        db.execSQL("ALTER TABLE evidence_drafts ADD COLUMN final_state TEXT NOT NULL DEFAULT 'NOT_PROCESSED'")
        db.execSQL("ALTER TABLE evidence_drafts ADD COLUMN final_relative_path TEXT")
        db.execSQL("ALTER TABLE evidence_drafts ADD COLUMN final_bytes INTEGER")
        db.execSQL("ALTER TABLE evidence_drafts ADD COLUMN final_sha256 TEXT")
        db.execSQL("ALTER TABLE evidence_drafts ADD COLUMN final_mime_type TEXT")
        db.execSQL("ALTER TABLE evidence_drafts ADD COLUMN final_width_px INTEGER")
        db.execSQL("ALTER TABLE evidence_drafts ADD COLUMN final_height_px INTEGER")
        db.execSQL("ALTER TABLE evidence_drafts ADD COLUMN final_duration_millis INTEGER")
        db.execSQL("ALTER TABLE evidence_drafts ADD COLUMN vault_relative_path TEXT")

        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS `outbox_items` (
                `id` TEXT NOT NULL,
                `assessmentId` TEXT NOT NULL,
                `revision_id` TEXT NOT NULL,
                `idempotency_key` TEXT NOT NULL,
                `kind` TEXT NOT NULL,
                `evidence_id` TEXT,
                `task_id` TEXT,
                `vault_relative_path` TEXT NOT NULL,
                `priority` INTEGER NOT NULL,
                `created_at_millis` INTEGER NOT NULL,
                `retry_count` INTEGER NOT NULL DEFAULT 0,
                `last_attempt_at_millis` INTEGER,
                PRIMARY KEY(`id`),
                FOREIGN KEY(`assessmentId`) REFERENCES `assessment_drafts`(`id`) ON UPDATE NO ACTION ON DELETE CASCADE
            )
            """.trimIndent(),
        )
        db.execSQL("CREATE INDEX IF NOT EXISTS `index_outbox_items_assessmentId` ON `outbox_items` (`assessmentId`)")
        db.execSQL("CREATE INDEX IF NOT EXISTS `index_outbox_items_idempotencyKey` ON `outbox_items` (`idempotency_key`)")
    }
}

/** P6: adds the sync-progress columns to `outbox_items` (see [SyncState] and
 * [OutboxItemEntity]'s doc comment) -- real, additive migration, never
 * fallbackToDestructiveMigration, same reasoning as MIGRATION_1_2/2_3. A sealed,
 * not-yet-synced outbox row surviving an app update must never be silently wiped. */
val MIGRATION_3_4 = object : Migration(3, 4) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE outbox_items ADD COLUMN sync_state TEXT NOT NULL DEFAULT 'QUEUED'")
        db.execSQL("ALTER TABLE outbox_items ADD COLUMN server_session_id INTEGER")
        db.execSQL("ALTER TABLE outbox_items ADD COLUMN server_object_id INTEGER")
        db.execSQL("ALTER TABLE outbox_items ADD COLUMN bytes_uploaded INTEGER NOT NULL DEFAULT 0")
        db.execSQL("ALTER TABLE outbox_items ADD COLUMN last_error_category TEXT")
        db.execSQL("ALTER TABLE outbox_items ADD COLUMN receipt_verified_at_millis INTEGER")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN synced_at_millis INTEGER")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN server_assessment_id INTEGER")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN server_worker_token TEXT")
    }
}

/** P7: durable declaration/match snapshot (closes the P6/P3-disclosed gap where this was
 * ViewModel-scoped only), per-task reassessment lock state, and the worker-updates polling
 * cursor + cached report/reassessment status -- see AssessmentDraftEntity/TaskDraftEntity/
 * EvidenceDraftEntity's new P7 fields. Real, additive migration, never
 * fallbackToDestructiveMigration, same reasoning as MIGRATION_1_2/2_3/3_4. */
val MIGRATION_4_5 = object : Migration(4, 5) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN declaration_answers_json TEXT")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN declaration_years_of_experience INTEGER NOT NULL DEFAULT 0")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN declaration_free_text TEXT NOT NULL DEFAULT ''")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN declaration_work_setting TEXT")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN declaration_prior_training TEXT")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN match_output_json TEXT")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN current_revision_number INTEGER NOT NULL DEFAULT 1")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN worker_updates_cursor INTEGER NOT NULL DEFAULT 0")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN report_status TEXT NOT NULL DEFAULT 'none'")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN pending_reassessment_task_codes_csv TEXT")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN pending_reassessment_reason TEXT")
        db.execSQL("ALTER TABLE assessment_drafts ADD COLUMN pending_reassessment_capture_instructions TEXT")

        db.execSQL("ALTER TABLE task_drafts ADD COLUMN locked INTEGER NOT NULL DEFAULT 0")

        db.execSQL("ALTER TABLE evidence_drafts ADD COLUMN from_previous_revision INTEGER NOT NULL DEFAULT 0")
    }
}

val MIGRATION_5_6 = object : Migration(5, 6) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("""CREATE TABLE IF NOT EXISTS `evidence_assistance` (
            `evidenceId` TEXT NOT NULL, `assessmentId` TEXT NOT NULL, `taskId` TEXT NOT NULL,
            `revisionNumber` INTEGER NOT NULL, `generation` TEXT NOT NULL, `inputPath` TEXT NOT NULL,
            `inputSha256` TEXT NOT NULL, `durationMs` INTEGER, `status` TEXT NOT NULL, `stage` TEXT NOT NULL,
            `resultJson` TEXT, `sealedSnapshotJson` TEXT, `errorCategory` TEXT,
            PRIMARY KEY(`evidenceId`), FOREIGN KEY(`evidenceId`) REFERENCES `evidence_drafts`(`id`) ON UPDATE NO ACTION ON DELETE CASCADE
        )""")
        db.execSQL("CREATE INDEX IF NOT EXISTS `index_evidence_assistance_assessmentId` ON `evidence_assistance` (`assessmentId`)")
    }
}

@androidx.room.Database(
    entities = [AssessmentDraftEntity::class, TaskDraftEntity::class, EvidenceDraftEntity::class, OutboxItemEntity::class, AssistanceRecord::class],
    version = 6,
    exportSchema = true,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun assessmentDraftDao(): AssessmentDraftDao
    abstract fun taskDraftDao(): TaskDraftDao
    abstract fun evidenceDraftDao(): EvidenceDraftDao
    abstract fun outboxDao(): OutboxDao
    abstract fun assistanceDao(): AssistanceDao

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
                .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5, MIGRATION_5_6)
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
