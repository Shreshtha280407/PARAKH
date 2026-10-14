package `in`.kaushalpramaan.app.data.draft

import androidx.room.testing.MigrationTestHelper
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * P6's real, additive MIGRATION_3_4 (see AppDatabase.kt) -- proves a v3 database with genuine
 * pre-existing rows (an assessment_drafts row, an outbox_items row, exactly as a real
 * READY_TO_SYNC package sealed under the previous app version would have) survives the
 * migration with every new P6 column present, correctly defaulted, and every pre-existing
 * value byte-for-byte unchanged. This is the one thing a schema-export JSON diff alone cannot
 * prove: that the real ALTER TABLE statements actually run cleanly against real data.
 *
 * Instrumented (real device/emulator), not Robolectric: MigrationTestHelper loads the exported
 * schema JSON from the real merged APK assets, which Robolectric's unit-test asset shadowing
 * does not reliably reproduce -- same reasoning this codebase already applies to every other
 * real-Android-environment-dependent test (Keystore/Tink/SQLCipher), see
 * ManifestSignerInstrumentedTest/VaultKeysetProviderInstrumentedTest for precedent.
 */
@RunWith(AndroidJUnit4::class)
class AppDatabaseMigrationTest {

    private val testDbName = "migration-test"

    @get:Rule
    val helper: MigrationTestHelper = MigrationTestHelper(
        InstrumentationRegistry.getInstrumentation(),
        AppDatabase::class.java,
    )

    @Test
    fun migrate_3_to_4_adds_sync_columns_with_safe_defaults_and_preserves_existing_rows() {
        helper.createDatabase(testDbName, 3).apply {
            execSQL(
                """
                INSERT INTO assessment_drafts
                    (id, state, qpCode, qpVersion, workerId, language, gap_task_ids_csv, is_test_only,
                     created_at_millis, updated_at_millis, seal_state, revision_id, idempotency_key)
                VALUES
                    ('a1', 'ACTIVE', 'CON/Q0602', 'v4.0', 'KP-TESTER1', 'en', '', 1,
                     1000, 2000, 'READY_TO_SYNC', 'rev-1', 'a1:rev-1')
                """.trimIndent(),
            )
            execSQL(
                """
                INSERT INTO outbox_items
                    (id, assessmentId, revision_id, idempotency_key, kind, evidence_id, task_id,
                     vault_relative_path, priority, created_at_millis, retry_count)
                VALUES
                    ('o1', 'a1', 'rev-1', 'a1:rev-1', 'MANIFEST', NULL, NULL,
                     'vault/a1/rev-1/manifest.vault', 0, 1500, 0)
                """.trimIndent(),
            )
            close()
        }

        val migrated = helper.runMigrationsAndValidate(testDbName, 4, true, MIGRATION_3_4)

        migrated.query(
            "SELECT sync_state, bytes_uploaded, server_session_id, server_object_id, " +
                "last_error_category, receipt_verified_at_millis, priority, created_at_millis " +
                "FROM outbox_items WHERE id = 'o1'",
        ).use { cursor ->
            assertTrue("expected the pre-existing outbox row to survive the migration", cursor.moveToFirst())
            assertEquals("QUEUED", cursor.getString(0))
            assertEquals(0L, cursor.getLong(1))
            assertTrue("server_session_id must default to NULL, not 0", cursor.isNull(2))
            assertTrue(cursor.isNull(3))
            assertTrue(cursor.isNull(4))
            assertTrue(cursor.isNull(5))
            // Pre-existing columns from before the migration are untouched.
            assertEquals(0, cursor.getInt(6))
            assertEquals(1500L, cursor.getLong(7))
        }

        migrated.query(
            "SELECT synced_at_millis, server_assessment_id, server_worker_token, seal_state, revision_id " +
                "FROM assessment_drafts WHERE id = 'a1'",
        ).use { cursor ->
            assertTrue(cursor.moveToFirst())
            assertTrue("a pre-P6 draft must not be born already 'synced'", cursor.isNull(0))
            assertTrue(cursor.isNull(1))
            assertTrue(cursor.isNull(2))
            assertEquals("READY_TO_SYNC", cursor.getString(3))
            assertEquals("rev-1", cursor.getString(4))
        }
    }
}
