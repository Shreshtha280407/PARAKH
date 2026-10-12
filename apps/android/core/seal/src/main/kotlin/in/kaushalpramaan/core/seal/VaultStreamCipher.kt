package `in`.kaushalpramaan.core.seal

import com.google.crypto.tink.StreamingAead
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream

/**
 * Pure streaming encrypt/decrypt against an already-obtained Tink [StreamingAead] primitive
 * (P5 spec part G). Deliberately knows nothing about *how* that primitive's keyset was
 * obtained -- in production that is always [VaultKeysetProvider]'s Android Keystore-protected
 * keyset; in tests it can be any valid [StreamingAead], so this encrypt/decrypt/AAD-binding
 * logic is testable without a real device. Streams file-to-file in fixed-size chunks via
 * Tink's own encrypting/decrypting stream wrappers -- never loads a whole file into memory.
 */
object VaultStreamCipher {

    fun encryptFile(aead: StreamingAead, sourceFile: File, destFile: File, associatedData: ByteArray) {
        destFile.parentFile?.mkdirs()
        FileOutputStream(destFile).use { rawOut ->
            aead.newEncryptingStream(rawOut, associatedData).use { encryptingOut ->
                FileInputStream(sourceFile).use { input -> input.copyTo(encryptingOut) }
            }
        }
    }

    /** Throws (Tink's AEAD authentication failure) if [sourceFile] was not produced by
     * [encryptFile] with this exact [aead] keyset and this exact [associatedData] -- the
     * mechanism that makes ciphertext un-swappable between evidence items/assessments. */
    fun decryptFile(aead: StreamingAead, sourceFile: File, destFile: File, associatedData: ByteArray) {
        destFile.parentFile?.mkdirs()
        FileInputStream(sourceFile).use { rawIn ->
            aead.newDecryptingStream(rawIn, associatedData).use { decryptingIn ->
                FileOutputStream(destFile).use { output -> decryptingIn.copyTo(output) }
            }
        }
    }

    /** Builds the one associated-data byte string every P5 vault item is bound to: assessment
     * ID, revision ID, evidence ID (or a fixed logical id for the manifest/signature package
     * itself), and a logical role -- so ciphertext from one item can never be substituted for
     * another's, even within the same assessment. */
    fun associatedData(assessmentId: String, revisionId: String, evidenceId: String, role: String): ByteArray =
        "$assessmentId|$revisionId|$evidenceId|$role".encodeToByteArray()
}

/** The public-facing handle other modules (`:app`) actually hold -- wraps a [StreamingAead]
 * primitive so Tink types never need to appear in a caller's own imports. Obtained via
 * [VaultKeysetProvider.getOrCreateCipher]. */
class VaultCipher internal constructor(private val aead: StreamingAead) {
    fun encryptFile(sourceFile: File, destFile: File, associatedData: ByteArray) =
        VaultStreamCipher.encryptFile(aead, sourceFile, destFile, associatedData)

    fun decryptFile(sourceFile: File, destFile: File, associatedData: ByteArray) =
        VaultStreamCipher.decryptFile(aead, sourceFile, destFile, associatedData)
}
