package `in`.kaushalpramaan.app.data.assistance

import android.content.Context
import androidx.room.Room
import androidx.sqlite.db.SupportSQLiteDatabase
import androidx.sqlite.db.SupportSQLiteOpenHelper
import androidx.sqlite.db.framework.FrameworkSQLiteOpenHelperFactory
import androidx.test.core.app.ApplicationProvider
import `in`.kaushalpramaan.app.data.draft.*
import java.io.File
import java.util.UUID
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** Real v5 exported schema + populated SQLite file, then Room validates the additive
 * v6 migration. SQLCipher/Keystore opening is a separate physical-device requirement. */
@RunWith(RobolectricTestRunner::class)
class AssistanceMigrationTest {
    @Test fun populated_v5_database_preserves_drafts_seal_sync_reassessment_and_outbox() = runBlocking {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val name = "p8-migration-${UUID.randomUUID()}.db"
        val root = generateSequence(File(System.getProperty("user.dir"))) { it.parentFile }.first { File(it, "contracts").isDirectory }
        val schema = Json.parseToJsonElement(File(root, "apps/android/app/schemas/in.kaushalpramaan.app.data.draft.AppDatabase/5.json").readText()).jsonObject.getValue("database").jsonObject
        val helper = FrameworkSQLiteOpenHelperFactory().create(SupportSQLiteOpenHelper.Configuration.builder(context).name(name)
            .callback(object : SupportSQLiteOpenHelper.Callback(5) {
                override fun onCreate(db: SupportSQLiteDatabase) {
                    for (entity in schema.getValue("entities").jsonArray) {
                        val e = entity.jsonObject
                        db.execSQL(e.getValue("createSql").jsonPrimitive.content.replace("${'$'}{TABLE_NAME}", e.getValue("tableName").jsonPrimitive.content))
                        e["indices"]?.jsonArray?.forEach { db.execSQL(it.jsonObject.getValue("createSql").jsonPrimitive.content.replace("${'$'}{TABLE_NAME}", e.getValue("tableName").jsonPrimitive.content)) }
                    }
                    schema.getValue("setupQueries").jsonArray.forEach { db.execSQL(it.jsonPrimitive.content) }
                }
                override fun onUpgrade(db: SupportSQLiteDatabase, oldVersion: Int, newVersion: Int) = error("unexpected upgrade")
            }).build())
        helper.writableDatabase.apply {
            execSQL("""INSERT INTO assessment_drafts(id,state,qpCode,qpVersion,workerId,language,gap_task_ids_csv,is_test_only,created_at_millis,updated_at_millis,seal_state,revision_id,server_assessment_id,server_worker_token,current_revision_number,worker_updates_cursor,report_status,pending_reassessment_task_codes_csv) VALUES ('a','ACTIVE','CON/Q0602','v4.0','TEST','en','T4',1,1000,2000,'READY_TO_SYNC','old-revision',42,'test-token',2,37,'available','T4')""")
            execSQL("""INSERT INTO task_drafts(assessmentId,taskId,state,evidence_count,budget_bytes,captured_bytes,updated_at_millis,locked) VALUES('a','T1','READY',1,15728640,100,2000,1)""")
            execSQL("""INSERT INTO evidence_drafts(id,assessmentId,taskId,kind,relative_path,byte_size,created_at_millis,state,is_test_only,final_state,final_sha256,vault_relative_path,from_previous_revision) VALUES('e','a','T1','PHOTO','drafts/a/T1/e.jpg',100,1000,'READY',1,'SEALED','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','vault/e.vault',1)""")
            execSQL("""INSERT INTO outbox_items(id,assessmentId,revision_id,idempotency_key,kind,evidence_id,task_id,vault_relative_path,priority,created_at_millis,sync_state,bytes_uploaded,server_object_id,receipt_verified_at_millis) VALUES('o','a','old-revision','a:old-revision','EVIDENCE','e','T1','vault/e.vault',1,1500,'SYNCED',100,53,1800)""")
        }
        helper.close()
        val migrated = Room.databaseBuilder(context, AppDatabase::class.java, name).addMigrations(MIGRATION_5_6).build()
        try {
            val a = migrated.assessmentDraftDao().getById("a")!!
            assertEquals("test-token", a.serverWorkerToken)
            assertEquals(2, a.currentRevisionNumber)
            assertEquals(37L, a.workerUpdatesCursor)
            assertEquals("available", a.reportStatus)
            assertEquals("T4", a.pendingReassessmentTaskCodesCsv)
            assertEquals(SealState.READY_TO_SYNC, a.sealState)
            assertTrue(migrated.taskDraftDao().getOne("a", "T1")!!.locked)
            val evidence = migrated.evidenceDraftDao().getById("e")!!
            assertTrue(evidence.fromPreviousRevision)
            assertEquals(FinalEvidenceState.SEALED, evidence.finalState)
            assertEquals("a".repeat(64), evidence.finalSha256)
            val outbox = migrated.outboxDao().getById("o")!!
            assertEquals(SyncState.SYNCED, outbox.syncState)
            assertEquals(53L, outbox.serverObjectId)
            assertEquals(1800L, outbox.receiptVerifiedAtMillis)
            assertNull(migrated.assistanceDao().get("e"))
        } finally { migrated.close(); context.deleteDatabase(name) }
    }
}
