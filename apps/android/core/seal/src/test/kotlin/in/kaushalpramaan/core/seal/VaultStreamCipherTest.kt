package `in`.kaushalpramaan.core.seal

import com.google.crypto.tink.KeysetHandle
import com.google.crypto.tink.StreamingAead
import com.google.crypto.tink.streamingaead.StreamingAeadConfig
import com.google.crypto.tink.streamingaead.StreamingAeadKeyTemplates
import java.io.File
import kotlin.random.Random
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Before
import org.junit.Test

/**
 * [VaultStreamCipher] is pure encrypt/decrypt against whatever [StreamingAead] primitive it is
 * handed -- a fresh in-memory test keyset here exercises the exact same encryption logic the
 * production Android Keystore-protected keyset will use (see [VaultKeysetProvider], tested on
 * a real device in VaultKeysetProviderInstrumentedTest since Robolectric has no real
 * AndroidKeyStore provider).
 */
@Suppress("DEPRECATION")
class VaultStreamCipherTest {

    private lateinit var tempDir: File

    @Before
    fun setUp() {
        StreamingAeadConfig.register()
        tempDir = File.createTempFile("vault_cipher_test", "").apply {
            delete()
            mkdirs()
        }
    }

    private fun freshAead(): StreamingAead =
        KeysetHandle.generateNew(StreamingAeadKeyTemplates.AES256_GCM_HKDF_4KB).getPrimitive(StreamingAead::class.java)

    @Test
    fun encrypt_then_decrypt_round_trips_to_the_exact_original_bytes() {
        val aead = freshAead()
        val original = Random(1).nextBytes(300_000)
        val source = File(tempDir, "source.bin").apply { writeBytes(original) }
        val encrypted = File(tempDir, "encrypted.bin")
        val decrypted = File(tempDir, "decrypted.bin")
        val aad = VaultStreamCipher.associatedData("a1", "r1", "e1", "evidence")

        VaultStreamCipher.encryptFile(aead, source, encrypted, aad)
        VaultStreamCipher.decryptFile(aead, encrypted, decrypted, aad)

        assertArrayEquals(original, decrypted.readBytes())
        assertFalse("ciphertext must not equal plaintext", encrypted.readBytes().contentEquals(original))
    }

    @Test
    fun encrypted_file_is_unreadable_ciphertext_not_the_plaintext_header() {
        val aead = freshAead()
        val original = "KP-Seal plaintext evidence marker".encodeToByteArray()
        val source = File(tempDir, "source.bin").apply { writeBytes(original) }
        val encrypted = File(tempDir, "encrypted.bin")

        VaultStreamCipher.encryptFile(aead, source, encrypted, VaultStreamCipher.associatedData("a1", "r1", "e1", "evidence"))

        assertFalse(encrypted.readBytes().decodeToString().contains("KP-Seal"))
    }

    @Test
    fun decryption_fails_when_the_associated_data_does_not_match_swap_rejection() {
        val aead = freshAead()
        val source = File(tempDir, "source.bin").apply { writeBytes(Random(2).nextBytes(10_000)) }
        val encrypted = File(tempDir, "encrypted.bin")
        val decrypted = File(tempDir, "decrypted.bin")

        VaultStreamCipher.encryptFile(aead, source, encrypted, VaultStreamCipher.associatedData("assessment-A", "r1", "e1", "evidence"))

        // Same keyset, same ciphertext, but a DIFFERENT assessment/evidence id in the AAD --
        // simulates an attempt to relabel one item's ciphertext as belonging to another.
        assertThrows(Exception::class.java) {
            VaultStreamCipher.decryptFile(aead, encrypted, decrypted, VaultStreamCipher.associatedData("assessment-B", "r1", "e1", "evidence"))
        }
    }

    @Test
    fun decryption_fails_with_the_wrong_keyset() {
        val aead1 = freshAead()
        val aead2 = freshAead()
        val source = File(tempDir, "source.bin").apply { writeBytes(Random(3).nextBytes(10_000)) }
        val encrypted = File(tempDir, "encrypted.bin")
        val decrypted = File(tempDir, "decrypted.bin")
        val aad = VaultStreamCipher.associatedData("a1", "r1", "e1", "evidence")

        VaultStreamCipher.encryptFile(aead1, source, encrypted, aad)

        assertThrows(Exception::class.java) {
            VaultStreamCipher.decryptFile(aead2, encrypted, decrypted, aad)
        }
    }

    @Test
    fun decrypting_stream_reconstructs_the_exact_original_bytes_reading_in_small_chunks() {
        // P6: proves the bounded chunk-at-a-time read API (VaultStreamCipher.decryptingStream /
        // VaultCipher.openDecryptingStream) is byte-identical to the whole-file decryptFile path
        // -- the only difference is HOW the caller consumes it (small fixed-size reads, as the
        // real sync worker does, 1 MiB at a time), never materialising the full plaintext.
        val aead = freshAead()
        val original = Random(5).nextBytes(300_000)
        val source = File(tempDir, "source.bin").apply { writeBytes(original) }
        val encrypted = File(tempDir, "encrypted.bin")
        val aad = VaultStreamCipher.associatedData("a1", "r1", "e1", "evidence")
        VaultStreamCipher.encryptFile(aead, source, encrypted, aad)

        val reconstructed = java.io.ByteArrayOutputStream()
        val buffer = ByteArray(4096) // deliberately small/odd relative to the 300 KB payload
        VaultStreamCipher.decryptingStream(aead, encrypted, aad).use { stream ->
            var totalRead = 0
            while (true) {
                val n = stream.read(buffer)
                if (n < 0) break
                reconstructed.write(buffer, 0, n)
                totalRead += n
            }
            check(totalRead == original.size) { "expected $totalRead to equal ${original.size}" }
        }

        assertArrayEquals(original, reconstructed.toByteArray())
    }

    @Test
    fun decrypting_stream_fails_mid_read_on_a_tampered_ciphertext_not_just_on_open() {
        val aead = freshAead()
        val original = Random(6).nextBytes(500_000)
        val source = File(tempDir, "source.bin").apply { writeBytes(original) }
        val encrypted = File(tempDir, "encrypted.bin")
        val aad = VaultStreamCipher.associatedData("a1", "r1", "e1", "evidence")
        VaultStreamCipher.encryptFile(aead, source, encrypted, aad)
        val bytes = encrypted.readBytes()
        bytes[bytes.size - 1] = (bytes[bytes.size - 1] + 1).toByte() // tamper the last (authenticated) segment
        encrypted.writeBytes(bytes)

        assertThrows(Exception::class.java) {
            VaultStreamCipher.decryptingStream(aead, encrypted, aad).use { stream ->
                val buffer = ByteArray(4096)
                while (stream.read(buffer) >= 0) {
                    // keep reading until the tampered segment's auth tag fails
                }
            }
        }
    }

    @Test
    fun decryption_fails_after_a_one_byte_ciphertext_modification() {
        val aead = freshAead()
        val source = File(tempDir, "source.bin").apply { writeBytes(Random(4).nextBytes(50_000)) }
        val encrypted = File(tempDir, "encrypted.bin")
        val decrypted = File(tempDir, "decrypted.bin")
        val aad = VaultStreamCipher.associatedData("a1", "r1", "e1", "evidence")

        VaultStreamCipher.encryptFile(aead, source, encrypted, aad)
        val bytes = encrypted.readBytes()
        bytes[bytes.size / 2] = (bytes[bytes.size / 2] + 1).toByte()
        encrypted.writeBytes(bytes)

        assertThrows(Exception::class.java) {
            VaultStreamCipher.decryptFile(aead, encrypted, decrypted, aad)
        }
    }
}
