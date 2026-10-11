package `in`.kaushalpramaan.app

import `in`.kaushalpramaan.app.data.DeclarationCardCatalog
import `in`.kaushalpramaan.core.mapping.RulesLoader
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Guards the exact worker-facing declaration contract (20 cards + 6 tools,
 * match-rules@r3) and the electrical-safety notice requirements at the
 * Android UI layer -- complements (does not duplicate) the data-layer
 * checks already in core:mapping's MatcherTest/GoldenVectorsTest and the
 * static checks in tools/audit_qp_traceability.py and
 * tools/check_android_string_parity.py. This file catches the one failure
 * mode those cannot: a links.json id with no matching Android string
 * resource throwing at runtime, and the safety notice actually rendering
 * (not just being declared) on-screen.
 */
@RunWith(AndroidJUnit4::class)
class DeclarationContractAndSafetyTest {

    @get:Rule(order = 0)
    val clearDraftRule = ClearP4DraftBeforeTest()

    @get:Rule(order = 1)
    val composeRule = createAndroidComposeRule<MainActivity>()

    @Test
    fun declaration_contract_resolves_to_exactly_20_cards_and_6_tools() {
        // Exercises the exact production code path DeclarationScreen uses
        // (RulesLoader.load() + DeclarationCardCatalog) -- a links.json id
        // with no matching card_label_<id> string resource throws here.
        val rules = RulesLoader.load()
        val cardIds = DeclarationCardCatalog.allCards(rules).map { it.id }
        val toolIds = DeclarationCardCatalog.allTools(rules).map { it.id }
        assertEquals("expected exactly 20 declaration cards", 20, cardIds.size)
        assertEquals("expected exactly 6 tools", 6, toolIds.size)
        assertEquals("card ids must be unique", cardIds.size, cardIds.toSet().size)
        assertEquals("tool ids must be unique", toolIds.size, toolIds.toSet().size)
    }

    @Test
    fun safety_notice_is_displayed_before_task_execution_and_on_every_task() {
        composeRule.completeIntake(languageTag = "en")
        composeRule.answerAllDeclarationItems("often")
        composeRule.tapTag("btn_view_tasks")

        // Global notice on the task list, reached before any individual task
        // can be opened -- "before task execution".
        composeRule.onNodeWithTag("safety_notice").assertIsDisplayed()

        for (taskId in listOf("T1", "T2", "T3", "T4", "T5")) {
            // Each task card now also shows P4 status/count text, so fewer cards fit the
            // viewport than in P3 -- scroll the LazyColumn container itself (see
            // tapInLazyColumn's own doc comment for why a plain tapTag can't reach a
            // not-yet-composed card).
            composeRule.tapInLazyColumn("task_list_lazy_column", "task_card_$taskId")
            composeRule.onNodeWithTag("safety_notice").assertIsDisplayed()
            composeRule.tapTag("btn_back_to_tasks")
        }
    }

    @Test
    fun work_setting_and_prior_training_are_optional_and_never_change_the_match_result() {
        composeRule.completeIntake(languageTag = "en")

        // Select a work-setting and a prior-training chip and confirm they show
        // as selected -- then answer every declaration item "never" (the same
        // scenario ml/mapping/golden_vectors.jsonl's G003 pins to overall_coverage
        // 0.0 / not_appropriate_match) and confirm the ON-SCREEN result still
        // matches G003 exactly. If workSetting/priorTraining ever leaked into
        // the matcher, this would no longer be a clean all-never result.
        composeRule.tapInLazyColumn("declaration_lazy_column", "work_setting_construction_site")
        composeRule.onNodeWithTag("work_setting_construction_site").assertIsSelected()
        composeRule.tapInLazyColumn("declaration_lazy_column", "prior_training_informal_on_the_job")
        composeRule.onNodeWithTag("prior_training_informal_on_the_job").assertIsSelected()

        for (id in ALL_DECLARATION_ITEM_IDS) {
            composeRule.tapInLazyColumn("declaration_lazy_column", "answer_${id}_never")
        }
        composeRule.tapInLazyColumn("declaration_lazy_column", "btn_see_match")

        composeRule.onNodeWithText("Not an appropriate match right now").assertIsDisplayed()
        composeRule.onNodeWithText("Overall declared-experience coverage: 0%").assertIsDisplayed()
    }
}
