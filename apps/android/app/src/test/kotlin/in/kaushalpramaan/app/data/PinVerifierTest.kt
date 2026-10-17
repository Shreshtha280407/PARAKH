package `in`.kaushalpramaan.app.data

import org.junit.Assert.*
import org.junit.Test

class PinVerifierTest {
    @Test fun saltedVerifierAcceptsOnlyCorrectPinAndClearsInput() {
        val salt = PinVerifier.salt()
        val input = "1847".toCharArray()
        val verifier = PinVerifier.derive(input, salt)
        assertTrue(input.all { it == '\u0000' })
        assertTrue(PinVerifier.matches("1847".toCharArray(), salt, verifier))
        assertFalse(PinVerifier.matches("1848".toCharArray(), salt, verifier))
        assertFalse(verifier.contentEquals(PinVerifier.derive("1847".toCharArray(), PinVerifier.salt())))
        assertTrue(PinVerifier.ITERATIONS >= 600_000)
    }
    @Test(expected = IllegalArgumentException::class) fun nonNumericPinRejected() {
        PinVerifier.derive("12ab".toCharArray(), PinVerifier.salt())
    }
}
