package `in`.kaushalpramaan.app.data

import `in`.kaushalpramaan.app.R

/** UI-only grouping and localized-label lookup for declaration cards/tools.
 * Never used by the matcher itself (that reads packs/ae-con-q0602/mapping
 * directly via core:mapping) -- this only decides which heading a card is
 * shown under and which @string resource holds its EN/HI label. */

enum class DeclarationSection(val titleRes: Int) {
    PRACTICAL(R.string.declaration_section_tools),
    TOOLS_GRID(R.string.declaration_section_tools_grid),
    SAFETY(R.string.declaration_section_safety),
    TEAMWORK(R.string.declaration_section_teamwork),
    PLANNING(R.string.declaration_section_planning),
}

data class DeclarationCardUi(val id: String, val labelRes: Int, val section: DeclarationSection)

private fun cardLabelRes(id: String): Int {
    val resName = "card_label_${id.lowercase()}"
    return cardLabelResourceMap[resName]
        ?: throw IllegalStateException("no label resource for declaration item $id (expected $resName in card_labels.xml)")
}

/** Built once from the generated R class via reflection-free explicit mapping
 * would be 51 entries either way -- this indirection exists so a missing
 * translation fails fast with a clear message instead of a silent R.string
 * resolution error. Populated by DeclarationCardCatalog.allCards() below. */
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
        "card_label_c21" to R.string.card_label_c21, "card_label_c22" to R.string.card_label_c22,
        "card_label_c23" to R.string.card_label_c23, "card_label_c24" to R.string.card_label_c24,
        "card_label_c25" to R.string.card_label_c25, "card_label_c26" to R.string.card_label_c26,
        "card_label_c27" to R.string.card_label_c27,
        "card_label_s01" to R.string.card_label_s01, "card_label_s02" to R.string.card_label_s02,
        "card_label_s03" to R.string.card_label_s03, "card_label_s04" to R.string.card_label_s04,
        "card_label_s05" to R.string.card_label_s05, "card_label_s06" to R.string.card_label_s06,
        "card_label_s07" to R.string.card_label_s07, "card_label_s08" to R.string.card_label_s08,
        "card_label_tm01" to R.string.card_label_tm01, "card_label_tm02" to R.string.card_label_tm02,
        "card_label_tm03" to R.string.card_label_tm03, "card_label_tm04" to R.string.card_label_tm04,
        "card_label_pl01" to R.string.card_label_pl01, "card_label_pl02" to R.string.card_label_pl02,
        "card_label_pl03" to R.string.card_label_pl03, "card_label_pl04" to R.string.card_label_pl04,
        "card_label_tl01" to R.string.card_label_tl01, "card_label_tl02" to R.string.card_label_tl02,
        "card_label_tl03" to R.string.card_label_tl03, "card_label_tl04" to R.string.card_label_tl04,
        "card_label_tl05" to R.string.card_label_tl05, "card_label_tl06" to R.string.card_label_tl06,
        "card_label_tl07" to R.string.card_label_tl07, "card_label_tl08" to R.string.card_label_tl08,
    )
}

object DeclarationCardCatalog {
    private val practicalIds = (1..27).map { "C%02d".format(it) }
    private val safetyIds = (1..8).map { "S%02d".format(it) }
    private val teamworkIds = (1..4).map { "TM%02d".format(it) }
    private val planningIds = (1..4).map { "PL%02d".format(it) }
    private val toolIds = (1..8).map { "TL%02d".format(it) }

    fun allCards(): List<DeclarationCardUi> =
        practicalIds.map { DeclarationCardUi(it, cardLabelRes(it), DeclarationSection.PRACTICAL) } +
            safetyIds.map { DeclarationCardUi(it, cardLabelRes(it), DeclarationSection.SAFETY) } +
            teamworkIds.map { DeclarationCardUi(it, cardLabelRes(it), DeclarationSection.TEAMWORK) } +
            planningIds.map { DeclarationCardUi(it, cardLabelRes(it), DeclarationSection.PLANNING) }

    fun allTools(): List<DeclarationCardUi> =
        toolIds.map { DeclarationCardUi(it, cardLabelRes(it), DeclarationSection.TOOLS_GRID) }
}

fun taskTitleRes(taskId: String): Int = when (taskId.uppercase()) {
    "T1" -> R.string.task_title_t1
    "T2" -> R.string.task_title_t2
    "T3" -> R.string.task_title_t3
    "T4" -> R.string.task_title_t4
    "T5" -> R.string.task_title_t5
    else -> throw IllegalStateException("no localized title for task $taskId")
}
