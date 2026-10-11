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
        composeRule.onNodeWithText("शुरू करने से पहले").assertIsDisplayed() // "Before you start"
        composeRule.tapTag("consent_checkbox")
        composeRule.tapTag("btn_continue")

        // Registration screen in Hindi.
        composeRule.onNodeWithText("पंजीकरण करें").assertIsDisplayed() // "Register"
        composeRule.onNodeWithTag("reg_phone").performTextInput("9988776655")
        composeRule.onNodeWithTag("reg_pin").performTextInput("4321")
        composeRule.onNodeWithTag("reg_pin_confirm").performTextInput("4321")
        composeRule.tapTag("btn_register")

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

        // Preview + attestation + submit in Hindi.
        composeRule.onNodeWithText("यह प्रमाण मेरे अपने काम को दिखाता है।").assertIsDisplayed()
        composeRule.tapTag("attestation_checkbox")
        composeRule.tapTag("btn_submit")

        // submitted_title appears both in the top bar and the body -- assert via the
        // body's testTag rather than text to avoid an ambiguous "2 nodes found" match.
        composeRule.onNodeWithTag("submitted_title").assertIsDisplayed()
    }
}
