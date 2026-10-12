package `in`.kaushalpramaan.core.seal

import java.io.File
import java.security.MessageDigest

/** Streams a file through SHA-256 in fixed-size chunks -- never reads an entire file into
 * memory, so this is safe for arbitrarily large sealed video evidence (P5 spec part F.1). */
object StreamingHasher {
    private const val BUFFER_SIZE = 64 * 1024

    fun sha256Hex(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(BUFFER_SIZE)
            while (true) {
                val read = input.read(buffer)
                if (read == -1) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().toHexString()
    }

    fun ByteArray.toHexString(): String {
        val hexChars = "0123456789abcdef"
        val out = CharArray(size * 2)
        forEachIndexed { i, byte ->
            val v = byte.toInt() and 0xFF
            out[i * 2] = hexChars[v ushr 4]
            out[i * 2 + 1] = hexChars[v and 0x0F]
        }
        return String(out)
    }
}
