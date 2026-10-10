package `in`.kaushalpramaan.app

import `in`.kaushalpramaan.app.data.DeclarationCardCatalog
import `in`.kaushalpramaan.core.mapping.RulesLoader
import androidx.compose.ui.test.SemanticsNodeInteraction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.ComposeTestRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTextInput

/** Scrolls into view when the node sits inside a scrollable container;
 * tolerates screens with no scroll container at all (performScrollTo()
 * throws AssertionError there rather than being a no-op). */
fun SemanticsNodeInteraction.scrollToIfPossible(): SemanticsNodeInteraction {
    try {
        performScrollTo()
    } catch (_: AssertionError) {
        // no scrollable ancestor -- the node is already on-screen
    }
    return this
}

/** Shared navigation helpers for the instrumented P-3 journey tests. Every
 * screen is driven through real taps on the testTags set on production
 * composables (see each screen file) -- not through ViewModel shortcuts --
 * so these tests exercise the actual wired-up UI, not just the business
 * logic (which GoldenVectorsTest/MatcherTest in core:mapping already cover
 * exhaustively). */

val ALL_DECLARATION_ITEM_IDS: List<String> by lazy {
    val rules = RulesLoader.load()
    (DeclarationCardCatalog.allCards(rules) + DeclarationCardCatalog.allTools(rules)).map { it.id }
}

fun ComposeTestRule.tapTag(tag: String) {
    onNodeWithTag(tag).scrollToIfPossible().performClick()
}

/** language -> consent -> registration, ending on the declaration screen. */
fun ComposeTestRule.completeIntake(languageTag: String, phone: String = "9876543210", pin: String = "1234") {
    if (languageTag == "hi") {
        tapTag("lang_option_hi")
    } else {
        tapTag("lang_option_en")
    }
    tapTag("btn_continue")

    tapTag("consent_checkbox")
    tapTag("btn_continue")

    onNodeWithTag("reg_phone").scrollToIfPossible().performTextInput(phone)
    onNodeWithTag("reg_pin").scrollToIfPossible().performTextInput(pin)
    onNodeWithTag("reg_pin_confirm").scrollToIfPossible().performTextInput(pin)
    tapTag("btn_register")
}

/** DeclarationScreen's list is a LazyColumn (26 items + the non-scored
 * work-setting/prior-training/free-text block): a far-off item's
 * semantics node does not exist at all until it scrolls into the composed
 * window, so onNodeWithTag(tag).performScrollTo() can't find it to scroll to
 * it (chicken-and-egg). performScrollToNode() instead scrolls the CONTAINER
 * (declaration_lazy_column) using the lazy list's own index-aware scroll
 * action while searching for the matcher, which works for not-yet-composed
 * items. */
fun ComposeTestRule.tapInLazyColumn(containerTag: String, targetTag: String) {
    onNodeWithTag(containerTag).performScrollToNode(hasTestTag(targetTag))
    onNodeWithTag(targetTag).performClick()
}

/** Sets the same often/sometimes/never answer on every one of the 26
 * declaration items (20 cards + 6 tools), then taps through to the match
 * result screen. Used for
 * the three clean reference scenarios (all-often -> appropriate_match,
 * all-sometimes -> partial_match, all-never -> not_appropriate_match) that
 * ml/mapping/golden_vectors.jsonl G001/G002/G003 already pin exactly, so
 * the expected on-screen result here is known, not guessed. */
fun ComposeTestRule.answerAllDeclarationItems(answer: String) {
    for (id in ALL_DECLARATION_ITEM_IDS) {
        tapInLazyColumn("declaration_lazy_column", "answer_${id}_$answer")
    }
    tapInLazyColumn("declaration_lazy_column", "btn_see_match")
}
