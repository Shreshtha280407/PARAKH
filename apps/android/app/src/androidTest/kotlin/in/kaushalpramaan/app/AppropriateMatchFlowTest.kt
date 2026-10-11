package `in`.kaushalpramaan.app

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Full journey, English, "everything often" declaration -- pinned by
 * ml/mapping/golden_vectors.jsonl G001 to overall_coverage 0.9126,
 * match_result appropriate_match, gap_nos=[]. Proves: language -> consent ->
 * registration -> declaration -> match -> task list -> preview -> attestation
 * -> local submit -> sealed state, with an APPROPRIATE result showing its
 * "because" reasons and no gap badges. Evidence is not required to submit
 * (see PreviewScreen's submit button, gated only on the attestation
 * checkbox) so this journey deliberately does not touch the camera --
 * real in-app capture is covered by EvidenceCaptureFlowTest and, with a
 * human granting the permission, by the manual P4 device gate.
 */
@RunWith(AndroidJUnit4::class)
class AppropriateMatchFlowTest {

    @get:Rule(order = 0)
    val clearDraftRule = ClearP4DraftBeforeTest()

    @get:Rule(order = 1)
    val composeRule = createAndroidComposeRule<MainActivity>()

    @Test
    fun appropriate_match_journey_completes_end_to_end() {
        composeRule.completeIntake(languageTag = "en")
        composeRule.answerAllDeclarationItems("often")

        // Match result: appropriate, reasons ("because" lines) visible, no gaps.
        composeRule.onNodeWithTag("match_result_card").assertIsDisplayed()
        composeRule.onNodeWithText("Appropriate match").assertIsDisplayed()
        composeRule.onNodeWithText("Why this result").assertIsDisplayed()
        composeRule.onNodeWithText("No gap areas — nice work declaring experience across all areas.").assertIsDisplayed()

        composeRule.tapTag("btn_view_tasks")
        composeRule.onNodeWithTag("task_card_T1").assertIsDisplayed()

        composeRule.tapTag("btn_preview")
        composeRule.tapTag("attestation_checkbox")
        composeRule.tapTag("btn_submit")

        // submitted_title text also appears in the top bar, so assert via testTag
        // (the body copy, tagged) rather than text to avoid an ambiguous match.
        composeRule.onNodeWithTag("submitted_title").assertIsDisplayed()

        NetworkAssertions.assertAppHasNoInternetCapability(composeRule.activity)
    }
}
