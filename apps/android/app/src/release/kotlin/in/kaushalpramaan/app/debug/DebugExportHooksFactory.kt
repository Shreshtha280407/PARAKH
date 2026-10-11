package `in`.kaushalpramaan.app.debug

import `in`.kaushalpramaan.app.data.draft.AppDatabase
import `in`.kaushalpramaan.app.data.draft.EvidenceFileManager
import `in`.kaushalpramaan.core.seal.VaultKeysetProvider

/** Release-build counterpart of app/src/debug's real factory of the same name/signature (see
 * DebugExportHooks.kt). The real decrypting implementation is not merely disabled here -- it
 * does not exist in this source set at all, so it is genuinely absent from a release build's
 * compiled output (spec part H.3/H.7), not just runtime-gated. */
fun provideDebugExportHooks(
    database: AppDatabase,
    fileManager: EvidenceFileManager,
    vaultKeysetProvider: VaultKeysetProvider,
): DebugExportHooks = NoOpDebugExportHooks

private object NoOpDebugExportHooks : DebugExportHooks {
    override val isAvailable: Boolean = false
    override suspend fun export(assessmentId: String): DebugExportSummary? = null
    override fun cleanup(assessmentId: String) = Unit
}
