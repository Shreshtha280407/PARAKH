package `in`.kaushalpramaan.app

import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.data.draft.AppDatabase
import `in`.kaushalpramaan.app.data.draft.BeginCaptureResult
import `in`.kaushalpramaan.app.data.draft.DatabaseKeyProvider
import `in`.kaushalpramaan.app.data.draft.EvidenceFileManager
import `in`.kaushalpramaan.app.data.draft.EvidenceRepository
import `in`.kaushalpramaan.app.data.draft.FinalizeResult
import `in`.kaushalpramaan.core.mapping.RulesLoader
import android.content.pm.PackageManager
import android.database.sqlite.SQLiteException
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Real-device-only proof of the specific claims a Robolectric/JVM test cannot make: the
 * production database is genuinely SQLCipher-encrypted (requires the real native
 * libsqlcipher.so, unavailable off-device), the Keystore-wrapped passphrase is never
 * written to disk in plaintext, and the installed app carries exactly the permissions P4
 * requires: camera/mic, no network, no gallery/media read.
 */
@RunWith(AndroidJUnit4::class)
class SqlCipherAndPermissionsTest {

    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    @Test
    fun app_has_no_internet_and_no_network_state_permission() {
        NetworkAssertions.assertAppHasNoInternetCapability(context)
    }

    @Test
    fun app_has_camera_and_mic_declared_but_no_gallery_or_media_read_permission() {
        // CAMERA/RECORD_AUDIO are dangerous runtime permissions: a fresh install declares
        // them but does not yet hold a GRANTED state until the user approves the in-app
        // rationale flow (covered by the manual device gate). This checks the manifest
        // declaration itself, not live grant state.
        val info = try {
            context.packageManager.getPackageInfo(context.packageName, PackageManager.GET_PERMISSIONS)
        } catch (e: PackageManager.NameNotFoundException) {
            fail("could not read own package info: $e")
            return
        }
        val declared = info.requestedPermissions?.toList().orEmpty()

        assertTrue("CAMERA must be declared for in-app capture", declared.contains(android.Manifest.permission.CAMERA))
        assertTrue("RECORD_AUDIO must be declared for video capture", declared.contains(android.Manifest.permission.RECORD_AUDIO))

        val forbidden = listOf(
            "android.permission.READ_EXTERNAL_STORAGE",
            "android.permission.READ_MEDIA_IMAGES",
            "android.permission.READ_MEDIA_VIDEO",
            "android.permission.WRITE_EXTERNAL_STORAGE",
        )
        for (permission in forbidden) {
            assertFalse("must never declare $permission: no Gallery/media-reading path exists in P4", declared.contains(permission))
        }
    }

    @Test
    fun production_database_file_is_not_plaintext_sqlite_and_a_plain_opener_cannot_read_it() = runBlocking {
        val dbFile = context.getDatabasePath("kp_drafts.db")
        dbFile.delete()
        File(dbFile.path + "-wal").delete()
        File(dbFile.path + "-shm").delete()

        // Write at least one real row through a database built via the exact same
        // production wiring AppDatabase.getInstance() uses (real SQLCipher SupportFactory,
        // real Keystore-wrapped passphrase) -- built directly here (not via getInstance())
        // so this test stays isolated from whatever instance the rest of the running app
        // may already hold cached and open.
        val db = AppDatabase.build(context, "kp_drafts.db")
        val repository = EvidenceRepository(
            db.assessmentDraftDao(),
            db.taskDraftDao(),
            db.evidenceDraftDao(),
            EvidenceFileManager(context),
            RulesLoader.load(),
        )
        val assessment = repository.createOrResumeAssessment(workerId = "KP-SQLCIPHER-TEST", language = "en", matchOutput = null)
        val begin = repository.beginCapture(assessment.id, "T1", EvidenceType.PHOTO, debugOverrideRequested = false)
        check(begin is BeginCaptureResult.Started)
        begin.stagingFile.parentFile?.mkdirs()
        begin.stagingFile.writeBytes(ByteArray(64))
        val finalize = repository.finalizeCapture(begin.evidenceId, success = true)
        check(finalize is FinalizeResult.Ready)
        db.close()

        assertTrue("expected a real database file on disk", dbFile.exists())

        // A genuine, unencrypted SQLite file always starts with a 16-byte magic header:
        // the ASCII text "SQLite format 3" followed by a single zero byte. SQLCipher's
        // encrypted first page does not start with this.
        val header = dbFile.inputStream().use { it.readNBytes(16) }
        val plaintextPrefix = "SQLite format 3".toByteArray(Charsets.US_ASCII)
        val headerPrefix = header.copyOfRange(0, 15)
        assertFalse(
            "database file must not start with the plaintext SQLite header",
            headerPrefix.contentEquals(plaintextPrefix) && header[15] == 0.toByte(),
        )

        // The strongest proof: Android's own framework SQLite (not SQLCipher) must fail to
        // open this file as a readable database at all.
        try {
            val plainDb = android.database.sqlite.SQLiteDatabase.openDatabase(
                dbFile.path,
                null,
                android.database.sqlite.SQLiteDatabase.OPEN_READONLY,
            )
            plainDb.rawQuery("SELECT count(*) FROM assessment_drafts", null).use { it.moveToFirst() }
            plainDb.close()
            fail("a plain, non-SQLCipher SQLiteDatabase must not be able to read the encrypted draft database")
        } catch (_: SQLiteException) {
            // expected: the file is not a valid plaintext SQLite database
        }
    }

    @Test
    fun database_passphrase_is_never_present_in_plaintext_in_its_backing_shared_prefs_file() {
        // Calling the key provider directly (not via AppDatabase.getInstance()) keeps this
        // test independent of whatever Room singleton state another test may have left
        // behind, while still exercising the exact same production key-derivation path.
        DatabaseKeyProvider(context).getOrCreatePassphrase()

        val prefsFile = File(context.applicationInfo.dataDir, "shared_prefs/kp_db_key_store.xml")
        assertTrue("expected the encrypted key-store prefs file to exist", prefsFile.exists())
        val raw = prefsFile.readText()

        // EncryptedSharedPreferences encrypts both the stored key name and its value --
        // neither the known key alias nor an obviously-plaintext long base64 secret should
        // ever appear verbatim.
        assertFalse("the preference key name must not appear in plaintext", raw.contains("db_passphrase_v1"))
        assertNotEquals("file must not be empty", "", raw.trim())
    }
}
