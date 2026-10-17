package `in`.kaushalpramaan.app

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import `in`.kaushalpramaan.app.data.CandidateSecurity
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class CandidateSecurityInstrumentedTest {
    @Test fun registrationSurvivesRestartAndLockoutCannotBeResetByReopening() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        check(context.packageName.endsWith(".p8validation")) { "Security tests require the isolated QA app" }
        val security = CandidateSecurity(context)
        security.clear() // Run only in the isolated .p8validation UID.
        try {
            val profile = security.register("Asha Kumar", "9876543210", false, "1847".toCharArray())
            val reopened = CandidateSecurity(context)
            assertEquals(profile, reopened.profile())
            assertTrue(reopened.unlock("1847".toCharArray()))
            val now = System.currentTimeMillis()
            repeat(5) { assertFalse(reopened.unlock("0000".toCharArray(), now)) }
            val restarted = CandidateSecurity(context)
            assertTrue(restarted.remainingLockMillis(now) >= 30_000)
            assertFalse(restarted.unlock("1847".toCharArray(), now))
            assertTrue(restarted.unlock("1847".toCharArray(), now + 31_000))
            val prefs = context.getSharedPreferences("kp_candidate_security", 0).all.toString()
            assertFalse(prefs.contains("1847"))
            assertFalse(prefs.contains("Asha Kumar"))
        } finally { security.clear() }
    }
}
