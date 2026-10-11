package `in`.kaushalpramaan.app.data.draft

import `in`.kaushalpramaan.app.data.EvidenceType
import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class EvidenceFileManagerTest {

    private lateinit var context: Context
    private lateinit var fileManager: EvidenceFileManager

    @Before
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        fileManager = EvidenceFileManager(context)
    }

    @Test
    fun staging_and_final_paths_are_app_private_and_never_a_mediastore_uri() {
        val staging = fileManager.stagingFile("a1", "T1", "e1", EvidenceType.PHOTO)
        val final = fileManager.finalFile("a1", "T1", "e1", EvidenceType.PHOTO)

        assertTrue(staging.absolutePath.startsWith(context.filesDir.absolutePath))
        assertTrue(final.absolutePath.startsWith(context.filesDir.absolutePath))
        assertEquals("e1.staging.jpg", staging.name)
        assertEquals("e1.jpg", final.name)
        assertFalse(staging.absolutePath.contains("content://"))
    }

    @Test
    fun video_extension_is_mp4() {
        val final = fileManager.finalFile("a1", "T2", "e2", EvidenceType.VIDEO)
        assertEquals("e2.mp4", final.name)
    }

    @Test
    fun promote_renames_staging_to_final_and_removes_staging() {
        val staging = fileManager.stagingFile("a1", "T1", "e1", EvidenceType.PHOTO)
        staging.parentFile?.mkdirs()
        staging.writeBytes(byteArrayOf(1, 2, 3))
        val final = fileManager.finalFile("a1", "T1", "e1", EvidenceType.PHOTO)

        val promoted = fileManager.promote(staging, final)

        assertTrue(promoted)
        assertFalse(staging.exists())
        assertTrue(final.exists())
        assertEquals(3L, final.length())
    }

    @Test
    fun promote_fails_cleanly_when_staging_file_is_missing() {
        val staging = fileManager.stagingFile("a1", "T1", "e1", EvidenceType.PHOTO)
        val final = fileManager.finalFile("a1", "T1", "e1", EvidenceType.PHOTO)

        val promoted = fileManager.promote(staging, final)

        assertFalse(promoted)
        assertFalse(final.exists())
    }

    @Test
    fun deleteAssessmentTree_removes_every_task_dir_under_it() {
        val fileA = fileManager.finalFile("a1", "T1", "e1", EvidenceType.PHOTO).apply { parentFile?.mkdirs(); writeBytes(byteArrayOf(1)) }
        val fileB = fileManager.finalFile("a1", "T2", "e2", EvidenceType.VIDEO).apply { parentFile?.mkdirs(); writeBytes(byteArrayOf(1)) }

        fileManager.deleteAssessmentTree("a1")

        assertFalse(fileA.exists())
        assertFalse(fileB.exists())
        assertFalse(fileManager.assessmentDir("a1").exists())
    }

    @Test
    fun deleteAssessmentTree_never_touches_a_different_assessments_files() {
        val keep = fileManager.finalFile("a-keep", "T1", "e1", EvidenceType.PHOTO).apply { parentFile?.mkdirs(); writeBytes(byteArrayOf(9)) }
        fileManager.finalFile("a-gone", "T1", "e2", EvidenceType.PHOTO).apply { parentFile?.mkdirs(); writeBytes(byteArrayOf(9)) }

        fileManager.deleteAssessmentTree("a-gone")

        assertTrue(keep.exists())
    }

    @Test
    fun listFilesIn_and_listTaskDirs_see_exactly_what_was_written() {
        fileManager.finalFile("a1", "T1", "e1", EvidenceType.PHOTO).apply { parentFile?.mkdirs(); writeBytes(byteArrayOf(1)) }
        fileManager.finalFile("a1", "T2", "e2", EvidenceType.PHOTO).apply { parentFile?.mkdirs(); writeBytes(byteArrayOf(1)) }

        val taskDirs = fileManager.listTaskDirs("a1")
        assertEquals(2, taskDirs.size)
        val filesInT1 = fileManager.listFilesIn(fileManager.taskDir("a1", "T1"))
        assertEquals(1, filesInT1.size)
        assertEquals("e1.jpg", filesInT1.first().name)
    }

    @Test
    fun relativePath_round_trips_through_resolve() {
        val final = fileManager.finalFile("a1", "T1", "e1", EvidenceType.PHOTO)
        final.parentFile?.mkdirs()
        final.writeBytes(byteArrayOf(7, 7))

        val relative = fileManager.relativePathOf(final)
        val resolved = fileManager.resolveRelativePath(relative)

        assertEquals(final.absolutePath, resolved.absolutePath)
        assertEquals(2L, resolved.length())
    }

    @Test
    fun min_free_bytes_required_is_300_mb() {
        assertEquals(300L * 1024 * 1024, EvidenceFileManager.MIN_FREE_BYTES_REQUIRED)
    }
}
