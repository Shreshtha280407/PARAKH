package `in`.kaushalpramaan.core.seal

import `in`.kaushalpramaan.core.seal.StreamingHasher.toHexString
import java.io.File
import java.security.MessageDigest
import kotlin.random.Random
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class StreamingHasherTest {

    @Test
    fun sha256Hex_matches_a_direct_MessageDigest_computation() {
        val bytes = Random(7).nextBytes(500_000)
        val file = File.createTempFile("hasher_test", ".bin").apply { writeBytes(bytes) }

        val streamed = StreamingHasher.sha256Hex(file)
        val direct = MessageDigest.getInstance("SHA-256").digest(bytes).toHexString()

        assertEquals(direct, streamed)
        assertEquals(64, streamed.length) // 32 bytes, hex-encoded
    }

    @Test
    fun sha256Hex_is_stable_across_buffer_boundary_sized_files() {
        // Exercises files that land exactly on, just under, and just over the internal
        // read-buffer boundary, where an off-by-one in the streaming loop would most likely
        // surface.
        for (size in listOf(0, 1, 65_535, 65_536, 65_537, 200_000)) {
            val bytes = Random(size).nextBytes(size)
            val file = File.createTempFile("hasher_boundary_$size", ".bin").apply { writeBytes(bytes) }
            val expected = MessageDigest.getInstance("SHA-256").digest(bytes).toHexString()
            assertEquals("mismatch at size=$size", expected, StreamingHasher.sha256Hex(file))
        }
    }

    @Test
    fun sha256Hex_differs_for_different_content() {
        val fileA = File.createTempFile("hasher_a", ".bin").apply { writeBytes(Random(1).nextBytes(1000)) }
        val fileB = File.createTempFile("hasher_b", ".bin").apply { writeBytes(Random(2).nextBytes(1000)) }
        assertNotEquals(StreamingHasher.sha256Hex(fileA), StreamingHasher.sha256Hex(fileB))
    }
}
