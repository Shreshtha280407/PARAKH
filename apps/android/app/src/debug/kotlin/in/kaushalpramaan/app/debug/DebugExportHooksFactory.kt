package `in`.kaushalpramaan.app.debug

import `in`.kaushalpramaan.app.BuildConfig
import `in`.kaushalpramaan.app.data.draft.AppDatabase
import `in`.kaushalpramaan.app.data.draft.EvidenceFileManager
import `in`.kaushalpramaan.app.data.draft.OutboxItemKind
import `in`.kaushalpramaan.app.data.draft.SealState
import `in`.kaushalpramaan.core.seal.ManifestSigner
import `in`.kaushalpramaan.core.seal.SealManifest
import `in`.kaushalpramaan.core.seal.SignedManifestPackage
import `in`.kaushalpramaan.core.seal.StreamingHasher
import `in`.kaushalpramaan.core.seal.VaultKeysetProvider
import `in`.kaushalpramaan.core.seal.VaultStreamCipher
import android.util.Base64
import java.io.File
import java.security.KeyFactory
import java.security.spec.X509EncodedKeySpec

/** Debug-build-only factory (see DebugExportHooks.kt's doc comment for why this file exists
 * only in app/src/debug). Decrypts a real sealed package using the real production
 * VaultKeysetProvider/ManifestSigner -- not a mock -- purely for the P5_TEST_ONLY physical
 * verification gate (spec part H). */
fun provideDebugExportHooks(
    database: AppDatabase,
    fileManager: EvidenceFileManager,
    vaultKeysetProvider: VaultKeysetProvider,
): DebugExportHooks = RealDebugExportHooks(database, fileManager, vaultKeysetProvider)

private class RealDebugExportHooks(
    private val database: AppDatabase,
    private val fileManager: EvidenceFileManager,
    private val vaultKeysetProvider: VaultKeysetProvider,
) : DebugExportHooks {

    override val isAvailable: Boolean get() = BuildConfig.P5_TEST_ONLY_DEBUG_EXPORT_ENABLED

    override suspend fun export(assessmentId: String): DebugExportSummary? {
        if (!isAvailable) return null
        val assessment = database.assessmentDraftDao().getById(assessmentId) ?: return null
        if (assessment.sealState != SealState.READY_TO_SYNC) return null
        val revisionId = assessment.revisionId ?: return null
        val outboxRows = database.outboxDao().getAllForAssessmentOnce(assessmentId)
        val manifestRow = outboxRows.firstOrNull { it.kind == OutboxItemKind.MANIFEST } ?: return null

        val exportDir = fileManager.debugExportDir(assessmentId).apply { mkdirs() }
        val cipher = vaultKeysetProvider.getOrCreateCipher()

        val manifestVaultFile = fileManager.resolveRelativePath(manifestRow.vaultRelativePath)
        val manifestPlainFile = File(exportDir, "manifest_package.json")
        cipher.decryptFile(
            manifestVaultFile,
            manifestPlainFile,
            VaultStreamCipher.associatedData(assessmentId, revisionId, "manifest", "manifest"),
        )
        val signedPackage = SignedManifestPackage.fromJsonBytes(manifestPlainFile.readBytes())
        val canonicalBytes = Base64.decode(signedPackage.manifestBase64, Base64.NO_WRAP)
        val manifest = SealManifest.CANONICAL_JSON.decodeFromString(SealManifest.serializer(), canonicalBytes.decodeToString())
        val publicKey = KeyFactory.getInstance("EC")
            .generatePublic(X509EncodedKeySpec(Base64.decode(signedPackage.signerPublicKeyBase64, Base64.NO_WRAP)))
        val signatureVerified = ManifestSigner.verify(canonicalBytes, Base64.decode(signedPackage.signatureBase64, Base64.NO_WRAP), publicKey)

        val items = outboxRows.filter { it.kind == OutboxItemKind.EVIDENCE }.map { row ->
            val evidenceId = requireNotNull(row.evidenceId)
            val manifestItem = manifest.evidence.first { it.evidenceId == evidenceId }
            val vaultFile = fileManager.resolveRelativePath(row.vaultRelativePath)
            val plainFile = File(exportDir, manifestItem.fileName)
            cipher.decryptFile(vaultFile, plainFile, VaultStreamCipher.associatedData(assessmentId, revisionId, evidenceId, "evidence"))
            DebugExportedItem(
                label = "${manifestItem.taskId}/${manifestItem.fileName}",
                file = plainFile,
                manifestSha256 = manifestItem.sha256,
                actualSha256 = StreamingHasher.sha256Hex(plainFile),
            )
        }
        return DebugExportSummary(exportDir, signatureVerified, items)
    }

    override fun cleanup(assessmentId: String) {
        fileManager.deleteDebugExportTree(assessmentId)
    }
}
