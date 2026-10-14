package `in`.kaushalpramaan.core.seal

import com.google.crypto.tink.StreamingAead
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.io.InputStream

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

    /** P6: a true bounded decrypting stream -- the caller reads it in fixed-size chunks (e.g.
     * 1 MiB) via [InputStream.read], uploading each chunk and discarding the buffer, so the
     * full decrypted plaintext is NEVER materialised as a file on disk or held whole in
     * memory (P6 security rule 4). Throws the same Tink AEAD authentication failure as
     * [decryptFile] on the first read if [sourceFile]/[associatedData] don't match what
     * [encryptFile] actually produced -- callers must not assume success until the stream is
     * fully consumed without an exception. The returned stream owns the underlying file
     * handle; callers must close it (`use { }`) exactly like any other InputStream. */
    fun decryptingStream(aead: StreamingAead, sourceFile: File, associatedData: ByteArray): InputStream {
        val rawIn = FileInputStream(sourceFile)
        return try {
            aead.newDecryptingStream(rawIn, associatedData)
        } catch (e: Exception) {
            rawIn.close()
            throw e
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

    /** P6: see [VaultStreamCipher.decryptingStream] -- a bounded, chunk-at-a-time read of a
     * vault item's plaintext that never touches disk or memory as a whole file. */
    fun openDecryptingStream(sourceFile: File, associatedData: ByteArray): InputStream =
        VaultStreamCipher.decryptingStream(aead, sourceFile, associatedData)
}
