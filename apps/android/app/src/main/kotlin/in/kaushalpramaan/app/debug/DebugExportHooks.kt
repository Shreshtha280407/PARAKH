package `in`.kaushalpramaan.app.debug

import java.io.File

/**
 * P5_TEST_ONLY debug-only verification export (spec part H). Only the interface and plain
 * data classes live in the shared `main` source set -- no logic. The real decrypting
 * implementation lives only in `app/src/debug` (compiled into debug builds only);
 * `app/src/release` provides a no-op. [in.kaushalpramaan.app.debug.provideDebugExportHooks]
 * is declared once per variant source set with an identical signature, so AGP compiles
 * exactly one body into any given build -- the real implementation is genuinely absent from
 * a release build's compiled output, not merely disabled by a runtime/BuildConfig check.
 */
interface DebugExportHooks {
    val isAvailable: Boolean

    /** Decrypts the given assessment's sealed vault package (manifest + every evidence item)
     * into a fresh app-private temporary debug export directory, verifying the signature and
     * every item's SHA-256 against the manifest as it goes. Returns null if unavailable or if
     * the assessment is not sealed. */
    suspend fun export(assessmentId: String): DebugExportSummary?

    /** Deletes the decrypted export directory for [assessmentId], if any. Safe to call
     * whether or not an export was ever produced. */
    fun cleanup(assessmentId: String)
}

data class DebugExportedItem(
    val label: String,
    val file: File,
    val manifestSha256: String,
    val actualSha256: String,
) {
    val hashMatches: Boolean get() = manifestSha256.equals(actualSha256, ignoreCase = true)
}

data class DebugExportSummary(
    val exportDir: File,
    val signatureVerified: Boolean,
    val items: List<DebugExportedItem>,
) {
    val allHashesMatch: Boolean get() = items.all { it.hashMatches }
}
