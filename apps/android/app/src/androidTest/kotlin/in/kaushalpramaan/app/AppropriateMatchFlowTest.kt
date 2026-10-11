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
 * registration -> declaration -> match -> task list -> review screen, with
 * an APPROPRIATE result showing its "because" reasons and no gap badges.
 *
 * P5 note: sealing now genuinely requires at least one real, optimized, attested evidence
 * item (see PreviewScreen's `canSeal`) -- it is no longer gated on the attestation checkbox
 * alone, unlike the P3 placeholder this test originally exercised. Real capture needs a
 * human-granted camera permission (OEM-restriction-dependent -- see EvidenceCaptureFlowTest's
 * doc comment), which this declaration/match journey test deliberately does not request, to
 * avoid making every worker-journey test flaky on that restriction. This test therefore ends
 * at the real review screen rather than tapping through attestation/seal; the full real
 * capture -> optimize -> attest -> seal pipeline is covered end to end by
 * EvidenceCaptureFlowTest and SealOrchestratorInstrumentedTest.
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

        // Real P5 review screen: attestation checkbox is present but correctly disabled
        // (no evidence captured in this declaration/match-focused journey -- see the class
        // doc comment).
        composeRule.onNodeWithTag("attestation_checkbox").scrollToIfPossible().assertIsDisplayed()
        composeRule.onNodeWithText("Before you seal").assertIsDisplayed()

        NetworkAssertions.assertAppHasNoInternetCapability(composeRule.activity)
    }
}
