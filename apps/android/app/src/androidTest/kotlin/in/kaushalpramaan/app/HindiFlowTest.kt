package `in`.kaushalpramaan.app

import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.waitUntilExactlyOneExists
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Automated end-to-end check only -- NOT a human usability study and NOT
 * evidence that an independent non-team person has completed this flow
 * unaided. This is a scripted Espresso/Compose UI test: it drives the full
 * journey with Hindi selected at the language screen and asserts that real
 * Hindi strings render at each major checkpoint, ending at the
 * sealed-locally state. The master plan's original P-3 exit criterion ("a
 * non-team person completes the flow in Hindi without help") describes a
 * human usability study, which is outside the approved technical IC-1A
 * scope; not claimed as completed here or anywhere in this codebase -- see
 * docs/gates/IC1A.md and docs/gates/P3.md.
 *
 * P5 note: sealing now genuinely requires at least one real, optimized, attested evidence
 * item -- the attestation checkbox is disabled until evidence exists and automatic
 * optimisation has run (see PreviewScreen's `canSeal`), unlike P3's placeholder "attest with
 * no evidence" stand-in this test originally exercised. Real capture needs a human-granted
 * camera permission (OEM-restriction-dependent -- see EvidenceCaptureFlowTest's doc comment),
 * which this declaration/match journey test deliberately does not request, to avoid making
 * every worker-journey test flaky on that restriction. This test therefore ends at the real
 * review screen (still verifying real Hindi string rendering there) rather than tapping
 * through attestation/seal; the full real capture -> optimize -> attest -> seal pipeline is
 * covered end to end by EvidenceCaptureFlowTest and SealOrchestratorInstrumentedTest.
 */
@RunWith(AndroidJUnit4::class)
class HindiFlowTest {

    @get:Rule(order = 0)
    val clearDraftRule = ClearP4DraftBeforeTest()

    @get:Rule(order = 1)
    val composeRule = createAndroidComposeRule<MainActivity>()

    @OptIn(ExperimentalTestApi::class)
    @Test
    fun hindi_flow_renders_hindi_and_completes_end_to_end() {
        // Wait for the language screen rather than tapping immediately -- the app always
        // shows a brief LOADING screen first (the one-time P4 draft-resume check) before
        // navigating here; see completeIntake's own doc comment in TestFlows.kt.
        composeRule.waitUntilExactlyOneExists(hasTestTag("lang_option_hi"), timeoutMillis = 10_000)
        composeRule.tapTag("lang_option_hi")
        composeRule.onNodeWithText("आगे बढ़ें").assertIsDisplayed() // "Continue"
        composeRule.tapTag("btn_continue")

        // Consent screen in Hindi.
        composeRule.onNodeWithTag("consent_heading").assertIsDisplayed() // "Before you start"
        composeRule.tapTag("consent_checkbox")
        composeRule.tapTag("btn_continue")

        // Registration screen in Hindi.
        composeRule.onNodeWithText("उम्मीदवार का विवरण").assertIsDisplayed()
        composeRule.onNodeWithTag("reg_name").performTextInput("आशा कुमार")
        composeRule.onNodeWithTag("reg_phone").performTextInput("9988776655")
        composeRule.onNodeWithTag("reg_pin").performTextInput("4321")
        composeRule.onNodeWithTag("reg_pin_confirm").performTextInput("4321")
        composeRule.tapTag("btn_register")
        composeRule.waitUntilExactlyOneExists(hasTestTag("declaration_lazy_column"), timeoutMillis = 15_000)

        // Declaration screen in Hindi -- answer everything "often" (अक्सर) for a
        // clean appropriate_match, same reference scenario as G001.
        composeRule.onNodeWithText("अपने अनुभव के बारे में बताएं").assertIsDisplayed()
        composeRule.answerAllDeclarationItems("often")

        // Match result in Hindi.
        composeRule.onNodeWithText("उपयुक्त मैच").assertIsDisplayed() // "Appropriate match"
        composeRule.tapTag("btn_view_tasks")

        // Task list in Hindi.
        composeRule.onNodeWithText("अभ्यास कार्य").assertIsDisplayed() // "Practice tasks"
        composeRule.tapTag("btn_preview")

        // Final review screen in Hindi -- real P5 attestation copy, real-rendered (not a
        // placeholder). The checkbox stays correctly disabled here (no evidence captured --
        // see the class doc comment), so this test verifies real string rendering for the
        // P5 screen without tapping through to seal.
        composeRule.onNodeWithTag("attestation_checkbox").scrollToIfPossible().assertIsDisplayed()
        composeRule.onNodeWithText("सील करने से पहले").assertIsDisplayed() // attestation_title
        composeRule.onNodeWithText("मैं पुष्टि करता/करती हूं कि यह प्रमाण मेरे अपने काम को दिखाता है।").assertIsDisplayed()
    }
}
