package `in`.kaushalpramaan.app.data.draft

import `in`.kaushalpramaan.app.data.EvidenceType
import android.content.Context
import android.os.StatFs
import java.io.File

/**
 * Owns the on-disk layout for P4 draft evidence: app-private internal storage only
 * (`Context.filesDir/drafts/<assessmentId>/<taskId>/<evidenceId>[.staging].<ext>`),
 * never MediaStore, Downloads, Pictures, DCIM, shared external storage, or a
 * cache-only directory that the OS could reclaim mid-review. Every method here is a
 * plain filesystem operation; the crash-safety ordering (rename-then-commit,
 * mark-then-remove) lives in [EvidenceRepository], which calls these primitives.
 */
open class EvidenceFileManager(context: Context) {

    private val filesDir: File = context.filesDir
    private val rootDir: File = File(filesDir, "drafts")

    fun taskDir(assessmentId: String, taskId: String): File =
        File(File(rootDir, assessmentId), taskId).apply { mkdirs() }

    fun assessmentDir(assessmentId: String): File = File(rootDir, assessmentId)

    fun extensionFor(kind: EvidenceType): String = if (kind == EvidenceType.PHOTO) "jpg" else "mp4"

    fun stagingFile(assessmentId: String, taskId: String, evidenceId: String, kind: EvidenceType): File =
        File(taskDir(assessmentId, taskId), "$evidenceId.staging.${extensionFor(kind)}")

    fun finalFile(assessmentId: String, taskId: String, evidenceId: String, kind: EvidenceType): File =
        File(taskDir(assessmentId, taskId), "$evidenceId.${extensionFor(kind)}")

    fun relativePathOf(file: File): String = file.relativeTo(filesDir).path

    fun resolveRelativePath(relativePath: String): File = File(filesDir, relativePath)

    /** Same-directory rename is an atomic filesystem operation on a single volume --
     * the promoted file either fully exists under its final name or the staging file
     * is untouched; there is no partially-written intermediate on disk either way. */
    fun promote(staging: File, final: File): Boolean {
        if (!staging.exists()) return false
        final.parentFile?.mkdirs()
        return staging.renameTo(final)
    }

    fun deleteQuietly(file: File) {
        if (file.exists()) file.delete()
    }

    fun deleteAssessmentTree(assessmentId: String) {
        assessmentDir(assessmentId).deleteRecursively()
    }

    fun listAssessmentDirs(): List<File> = rootDir.listFiles()?.filter { it.isDirectory }.orEmpty()

    fun listTaskDirs(assessmentId: String): List<File> =
        assessmentDir(assessmentId).listFiles()?.filter { it.isDirectory }.orEmpty()

    fun listFilesIn(dir: File): List<File> = dir.listFiles()?.filter { it.isFile }.orEmpty()

    /** Bytes free on the internal-storage volume that backs [filesDir] -- the volume
     * all draft evidence actually lands on, not an external/removable one. */
    open fun availableInternalBytes(): Long = StatFs(filesDir.path).availableBytes

    companion object {
        const val MIN_FREE_BYTES_REQUIRED: Long = 300L * 1024 * 1024
    }
}
