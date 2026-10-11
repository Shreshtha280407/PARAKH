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

    // ---- P5: optimisation temp files, seal-time scratch files, encrypted vault ----

    /** Where a photo/video optimisation pass for one task's evidence writes its plaintext
     * output before adoption -- deleted once sealing succeeds (or once superseded by a
     * retake/replace/trim), never left to accumulate. */
    fun optimizationTempDir(assessmentId: String, taskId: String): File =
        File(File(File(filesDir, "p5_temp"), assessmentId), taskId).apply { mkdirs() }

    /** Scratch space for the plaintext canonical-manifest package during the brief window
     * between building it and encrypting it into the vault. */
    fun sealTempDir(assessmentId: String): File =
        File(File(File(filesDir, "p5_temp"), assessmentId), "_seal").apply { mkdirs() }

    /** App-private encrypted vault for one assessment revision's sealed package -- the only
     * place P5 final artifacts survive after a successful seal. */
    fun vaultDir(assessmentId: String, revisionId: String): File =
        File(File(File(filesDir, "vault"), assessmentId), revisionId).apply { mkdirs() }

    /** Debug-build-only (`P5_TEST_ONLY`) decrypted verification export -- excluded from
     * Gallery/backup/git, cleaned up explicitly; see the debug-only export feature. */
    fun debugExportDir(assessmentId: String): File =
        File(File(File(filesDir, "p5_debug_export"), assessmentId), System.currentTimeMillis().toString())

    fun deleteP5TempTree(assessmentId: String) {
        File(File(rootDir.parentFile, "p5_temp"), assessmentId).deleteRecursively()
    }

    fun deleteVaultTree(assessmentId: String) {
        File(File(filesDir, "vault"), assessmentId).deleteRecursively()
    }

    fun deleteDebugExportTree(assessmentId: String) {
        File(File(filesDir, "p5_debug_export"), assessmentId).deleteRecursively()
    }

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

    fun listP5TempAssessmentDirs(): List<File> =
        File(filesDir, "p5_temp").listFiles()?.filter { it.isDirectory }.orEmpty()

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
