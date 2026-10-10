package `in`.kaushalpramaan.app.data

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.core.mapping.Rules

/** UI-only grouping and localized-label lookup for declaration cards/tools.
 * Never used by the matcher itself (that reads packs/ae-con-q0602/mapping
 * directly via core:mapping) -- this only decides which heading a card is
 * shown under and which @string resource holds its EN/HI label.
 *
 * r3: card/tool ids are read from the loaded Rules (links.json), not a
 * hardcoded id range -- a links.json edit that changes the count or ids
 * is reflected here automatically; a genuinely missing translation still
 * fails fast (cardLabelRes throws) instead of silently resolving nothing. */

enum class DeclarationSection(val titleRes: Int) {
    PRACTICAL(R.string.declaration_section_tools),
    TOOLS_GRID(R.string.declaration_section_tools_grid),
}

data class DeclarationCardUi(val id: String, val labelRes: Int, val section: DeclarationSection)

private fun cardLabelRes(id: String): Int {
    val resName = "card_label_${id.lowercase()}"
    return cardLabelResourceMap[resName]
        ?: throw IllegalStateException("no label resource for declaration item $id (expected $resName in card_labels.xml)")
}

/** Exactly the 20 cards + 6 tools of the match-rules@r3 contract
 * (packs/ae-con-q0602/mapping/links.json). A links.json edit that adds or
 * removes an id without a matching entry here fails fast via cardLabelRes
 * above, rather than silently rendering a blank label. */
private val cardLabelResourceMap: Map<String, Int> by lazy {
    mapOf(
        "card_label_c01" to R.string.card_label_c01, "card_label_c02" to R.string.card_label_c02,
        "card_label_c03" to R.string.card_label_c03, "card_label_c04" to R.string.card_label_c04,
        "card_label_c05" to R.string.card_label_c05, "card_label_c06" to R.string.card_label_c06,
        "card_label_c07" to R.string.card_label_c07, "card_label_c08" to R.string.card_label_c08,
        "card_label_c09" to R.string.card_label_c09, "card_label_c10" to R.string.card_label_c10,
        "card_label_c11" to R.string.card_label_c11, "card_label_c12" to R.string.card_label_c12,
        "card_label_c13" to R.string.card_label_c13, "card_label_c14" to R.string.card_label_c14,
        "card_label_c15" to R.string.card_label_c15, "card_label_c16" to R.string.card_label_c16,
        "card_label_c17" to R.string.card_label_c17, "card_label_c18" to R.string.card_label_c18,
        "card_label_c19" to R.string.card_label_c19, "card_label_c20" to R.string.card_label_c20,
        "card_label_tl01" to R.string.card_label_tl01, "card_label_tl02" to R.string.card_label_tl02,
        "card_label_tl03" to R.string.card_label_tl03, "card_label_tl04" to R.string.card_label_tl04,
        "card_label_tl05" to R.string.card_label_tl05, "card_label_tl06" to R.string.card_label_tl06,
    )
}

object DeclarationCardCatalog {
    /** Cards in links.json document order -- the same order the worker sees them in. */
    fun allCards(rules: Rules): List<DeclarationCardUi> =
        rules.links.cards.map { DeclarationCardUi(it.id, cardLabelRes(it.id), DeclarationSection.PRACTICAL) }

    fun allTools(rules: Rules): List<DeclarationCardUi> =
        rules.links.tools.map { DeclarationCardUi(it.id, cardLabelRes(it.id), DeclarationSection.TOOLS_GRID) }
}

/** One selectable option in the non-scored work-setting / prior-training
 * fields below. The id is a plain string stored in DeclarationState and
 * NEVER read by Matcher.match -- see AppViewModel.computeMatch(), which only
 * passes declaration.answers and declaration.freeText to the matcher. */
data class ChoiceOptionUi(val id: String, val labelRes: Int)

object WorkSettingOptions {
    val options = listOf(
        ChoiceOptionUi("construction_site", R.string.work_setting_construction_site),
        ChoiceOptionUi("domestic_household", R.string.work_setting_domestic_household),
        ChoiceOptionUi("workshop_or_iti", R.string.work_setting_workshop_or_iti),
        ChoiceOptionUi("other", R.string.work_setting_other),
    )
}

object PriorTrainingOptions {
    val options = listOf(
        ChoiceOptionUi("iti_or_formal_course", R.string.prior_training_iti_or_formal_course),
        ChoiceOptionUi("informal_on_the_job", R.string.prior_training_informal_on_the_job),
        ChoiceOptionUi("none", R.string.prior_training_none),
        ChoiceOptionUi("other", R.string.prior_training_other),
    )
}

fun taskTitleRes(taskId: String): Int = when (taskId.uppercase()) {
    "T1" -> R.string.task_title_t1
    "T2" -> R.string.task_title_t2
    "T3" -> R.string.task_title_t3
    "T4" -> R.string.task_title_t4
    "T5" -> R.string.task_title_t5
    else -> throw IllegalStateException("no localized title for task $taskId")
}
