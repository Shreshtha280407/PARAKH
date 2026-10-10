package `in`.kaushalpramaan.app

import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performScrollToNode
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * "Everything sometimes" declaration -- pinned by
 * ml/mapping/golden_vectors.jsonl G002 to overall_coverage 0.5476,
 * match_result partial_match, gap_nos = all 5 practical NOS. Proves the
 * PARTIAL result shows its gaps on the match screen and that every one of
 * T1-T5 is marked "Extra evidence needed" on the task list.
 */
@RunWith(AndroidJUnit4::class)
class PartialMatchFlowTest {

    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    @Test
    fun partial_match_shows_gaps_and_flags_every_task() {
        composeRule.completeIntake(languageTag = "en")
        composeRule.answerAllDeclarationItems("sometimes")

        composeRule.onNodeWithText("Partial match — some gaps").assertIsDisplayed()
        composeRule.onNodeWithText("Areas with less declared experience").assertIsDisplayed()
        // All 5 practical NOS show up both in the "why" reasons and the gap list
        // (gap_nos == every practical NOS for an all-"sometimes" declaration) --
        // 2 occurrences each (because-line + gap-line) x 5 NOS = 10 nodes total.
        composeRule.onAllNodesWithText("CON/N", substring = true).assertCountEquals(10)

        composeRule.tapTag("btn_view_tasks")

        // The task list is a LazyColumn -- only the items that fit the viewport
        // are composed at once, so each task's gap badge must be scrolled to
        // individually (same reasoning as tapInLazyColumn in TestFlows.kt)
        // rather than counted with a single onAllNodesWithText across the
        // whole (virtualized) screen.
        for (taskId in listOf("T1", "T2", "T3", "T4", "T5")) {
            composeRule.onNodeWithTag("task_list_lazy_column").performScrollToNode(hasTestTag("task_gap_badge_$taskId"))
            composeRule.onNodeWithTag("task_gap_badge_$taskId").assertIsDisplayed()
        }
    }
}
