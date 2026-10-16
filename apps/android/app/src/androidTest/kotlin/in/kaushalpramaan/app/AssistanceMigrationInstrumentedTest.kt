package `in`.kaushalpramaan.app

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import `in`.kaushalpramaan.app.data.draft.*
import kotlinx.coroutines.runBlocking
import net.sqlcipher.database.SQLiteDatabase
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Upgrades an isolated, populated, genuinely encrypted v5 database using the production
 * Keystore-wrapped passphrase and AppDatabase builder. Never opens the worker's DB file. */
@RunWith(AndroidJUnit4::class)
class AssistanceMigrationInstrumentedTest {
    @Test fun encrypted_v5_to_v6_preserves_sealed_history_receipts_and_reassessment() = runBlocking {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val name = "p8-encrypted-migration-${System.nanoTime()}.db"
        val path = context.getDatabasePath(name).apply { parentFile!!.mkdirs() }
        SQLiteDatabase.loadLibs(context)
        val key = DatabaseKeyProvider(context).getOrCreatePassphrase()
        try {
            val schema = instrumentation.context.assets.open("in.kaushalpramaan.app.data.draft.AppDatabase/5.json")
                .bufferedReader().use { JSONObject(it.readText()).getJSONObject("database") }
            SQLiteDatabase.openOrCreateDatabase(path.absolutePath, key, null).use { old ->
                val entities = schema.getJSONArray("entities")
                for (i in 0 until entities.length()) {
                    val entity = entities.getJSONObject(i)
                    val table = entity.getString("tableName")
                    old.execSQL(entity.getString("createSql").replace("${'$'}{TABLE_NAME}", table))
                    val indices = entity.optJSONArray("indices")
                    if (indices != null) for (j in 0 until indices.length()) old.execSQL(indices.getJSONObject(j).getString("createSql").replace("${'$'}{TABLE_NAME}", table))
                }
                val setup = schema.getJSONArray("setupQueries")
                for (i in 0 until setup.length()) old.execSQL(setup.getString(i))
                old.execSQL("""INSERT INTO assessment_drafts(id,state,qpCode,qpVersion,workerId,language,gap_task_ids_csv,is_test_only,created_at_millis,updated_at_millis,seal_state,revision_id,current_revision_number,worker_updates_cursor,report_status,pending_reassessment_task_codes_csv) VALUES('p8-migration','ACTIVE','CON/Q0602','v4.0','SYNTHETIC','en','T4',1,1000,2000,'READY_TO_SYNC','historical-revision',2,37,'available','T4')""")
                old.execSQL("""INSERT INTO task_drafts(assessmentId,taskId,state,evidence_count,budget_bytes,captured_bytes,updated_at_millis,locked) VALUES('p8-migration','T1','READY',1,15728640,100,2000,1)""")
                old.execSQL("""INSERT INTO evidence_drafts(id,assessmentId,taskId,kind,relative_path,byte_size,created_at_millis,state,is_test_only,final_state,final_sha256,from_previous_revision) VALUES('p8-e','p8-migration','T1','PHOTO','synthetic/e.jpg',100,1000,'READY',1,'SEALED','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',1)""")
                old.execSQL("""INSERT INTO outbox_items(id,assessmentId,revision_id,idempotency_key,kind,evidence_id,task_id,vault_relative_path,priority,created_at_millis,sync_state,bytes_uploaded,server_object_id,receipt_verified_at_millis) VALUES('p8-o','p8-migration','historical-revision','p8-migration:historical-revision','EVIDENCE','p8-e','T1','synthetic/e.vault',1,1500,'SYNCED',100,53,1800)""")
                old.version = 5
            }
        } finally { key.fill(0) }
        val upgraded = AppDatabase.build(context, name)
        try {
            val assessment = upgraded.assessmentDraftDao().getById("p8-migration")!!
            assertEquals(2, assessment.currentRevisionNumber)
            assertEquals(37L, assessment.workerUpdatesCursor)
            assertEquals("T4", assessment.pendingReassessmentTaskCodesCsv)
            assertEquals("available", assessment.reportStatus)
            assertEquals(SealState.READY_TO_SYNC, assessment.sealState)
            val evidence = upgraded.evidenceDraftDao().getById("p8-e")!!
            assertEquals(FinalEvidenceState.SEALED, evidence.finalState)
            assertTrue(evidence.fromPreviousRevision)
            assertEquals("a".repeat(64), evidence.finalSha256)
            val outbox = upgraded.outboxDao().getById("p8-o")!!
            assertEquals(SyncState.SYNCED, outbox.syncState)
            assertEquals(53L, outbox.serverObjectId)
            assertEquals(1800L, outbox.receiptVerifiedAtMillis)
            assertNull(upgraded.assistanceDao().get("p8-e"))
        } finally { upgraded.close(); context.deleteDatabase(name) }
    }
}
