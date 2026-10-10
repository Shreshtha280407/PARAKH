package `in`.kaushalpramaan.app

import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performSemanticsAction
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Covers the mock-evidence budget workflow end to end: fill a task's
 * 15 MB (T1) budget exactly, prove a further add is rejected with a clear
 * message, then prove remove recalculates the task back to zero used, and
 * replace swaps an item in place (no duplicate). */
@RunWith(AndroidJUnit4::class)
class EvidenceBudgetTest {

    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    @Test
    fun budget_overflow_is_rejected_and_remove_replace_recalculate_correctly() {
        composeRule.completeIntake(languageTag = "en")
        // blank declaration is valid input -- not_appropriate_match. btn_see_match sits
        // at the bottom of DeclarationScreen's LazyColumn, so it must be reached via the
        // container's own scroll-to-node action, same as answerAllDeclarationItems().
        composeRule.tapInLazyColumn("declaration_lazy_column", "btn_see_match")
        composeRule.tapTag("btn_view_tasks")
        composeRule.tapTag("task_card_T1") // Safety & PPE, 15 MB budget

        // Fill the task's entire budget in one item.
        composeRule.tapTag("btn_add_evidence")
        composeRule.onNodeWithTag("evidence_size_slider").performSemanticsAction(SemanticsActions.SetProgress) {
            it(15_728_640f) // exactly 15 MB, T1's full budget (tasks.json)
        }
        composeRule.tapTag("btn_save_evidence")
        composeRule.onAllNodesWithTag("evidence_row").assertCountEquals(1)

        // A second add attempt must be rejected: nothing left in the task budget.
        composeRule.tapTag("btn_add_evidence")
        composeRule.onNodeWithText(
            "This would go over this task's evidence budget. Reduce the size or remove other evidence first.",
        ).assertIsDisplayed()
        composeRule.onNodeWithTag("btn_save_evidence").assertIsNotEnabled()
        composeRule.tapTag("btn_cancel_evidence_dialog")

        // Remove the item -> task must show "no evidence" again (budget back to 0).
        composeRule.tapTag("btn_remove_evidence_0")
        composeRule.onNodeWithText("No evidence added yet.").assertIsDisplayed()

        // Add one item, then replace it -- must still be exactly one item afterwards.
        composeRule.tapTag("btn_add_evidence")
        composeRule.onNodeWithTag("evidence_size_slider").performSemanticsAction(SemanticsActions.SetProgress) { it(5_000_000f) }
        composeRule.tapTag("btn_save_evidence")
        composeRule.tapTag("btn_replace_evidence_0")
        composeRule.onNodeWithTag("evidence_size_slider").performSemanticsAction(SemanticsActions.SetProgress) { it(8_000_000f) }
        composeRule.tapTag("btn_save_evidence")
        composeRule.onAllNodesWithTag("evidence_row", useUnmergedTree = true).assertCountEquals(1)
    }
}
