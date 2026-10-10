package `in`.kaushalpramaan.app

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performTextInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * P-3 exit test (master plan p.18): "A non-team person completes the flow
 * in Hindi without help." Drives the full journey with Hindi selected at
 * the language screen and asserts Hindi text renders at each major
 * checkpoint, ending at the sealed-locally state.
 */
@RunWith(AndroidJUnit4::class)
class HindiFlowTest {

    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    @Test
    fun hindi_flow_renders_hindi_and_completes_end_to_end() {
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
