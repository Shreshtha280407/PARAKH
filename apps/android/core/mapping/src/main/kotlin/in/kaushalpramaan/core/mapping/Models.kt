package `in`.kaushalpramaan.core.mapping

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Kotlin mirror of packs/ae-con-q0602/mapping/links.json, keywords.json,
 * thresholds.json and packs/ae-con-q0602/tasks.json. These files are the
 * single canonical source for both the Python matcher (ml/mapping/matcher.py)
 * and this one -- core:mapping's Gradle build copies them in verbatim (see
 * build.gradle.kts's syncPackResources task), never hand-duplicated.
 */

@Serializable
data class PcLink(
    val nos: String,
    val pc: String,
    val weight: Double,
)

@Serializable
data class DeclarationItem(
    val id: String,
    val label: String,
    val links: List<PcLink> = emptyList(),
)

@Serializable
data class LinksFile(
    @SerialName("match_rules_id") val matchRulesId: String,
    val cards: List<DeclarationItem> = emptyList(),
    val tools: List<DeclarationItem> = emptyList(),
)

@Serializable
data class PracticalNosEntry(
    val nos: String,
    val credits: Int,
)

@Serializable
data class DeclarationContract(
    @SerialName("card_count") val cardCount: Int,
    @SerialName("tool_count") val toolCount: Int,
)

@Serializable
data class ThresholdsFile(
    @SerialName("match_rules_id") val matchRulesId: String,
    @SerialName("answer_strength") val answerStrength: Map<String, Double>,
    @SerialName("practical_nos_for_matching") val practicalNosForMatching: List<PracticalNosEntry>,
    @SerialName("declaration_contract") val declarationContract: DeclarationContract? = null,
)

@Serializable
data class KeywordsFile(
    val cards: Map<String, Map<String, List<String>>> = emptyMap(),
)

@Serializable
data class TaskEntry(
    val id: String,
    val nos: String,
    val title: String = "",
    @SerialName("budget_mb") val budgetMb: Int = 0,
    @SerialName("budget_bytes") val budgetBytes: Long = 0,
    @SerialName("evidence_hint") val evidenceHint: String = "",
    @SerialName("step_guide") val stepGuide: List<String> = emptyList(),
    @SerialName("linked_pcs") val linkedPcs: List<String> = emptyList(),
)

@Serializable
data class TasksFile(
    @SerialName("qp_code") val qpCode: String = "",
    @SerialName("qp_version") val qpVersion: String = "",
    @SerialName("final_evidence_budget_mb") val finalEvidenceBudgetMb: Int = 0,
    @SerialName("final_evidence_budget_bytes") val finalEvidenceBudgetBytes: Long = 0,
    val tasks: List<TaskEntry> = emptyList(),
)

/** Everything the matcher needs, loaded once and reused across calls. */
data class Rules(
    val links: LinksFile,
    val keywords: KeywordsFile,
    val thresholds: ThresholdsFile,
    val nosTask: Map<String, String>,
    val tasksFile: TasksFile,
)

/** A worker self-declaration. Mirrors matcher.py's normalized dict form exactly. */
data class Declaration(
    val answers: Map<String, String> = emptyMap(),
    val freeText: String = "",
)

@Serializable
data class ApplicableTask(
    val task: String? = null,
    val nos: String,
    @SerialName("extra_evidence_needed") val extraEvidenceNeeded: Boolean,
)

@Serializable
data class MatchOutput(
    @SerialName("match_result") val matchResult: String,
    @SerialName("overall_coverage") val overallCoverage: Double,
    @SerialName("nos_coverage") val nosCoverage: Map<String, Double>,
    @SerialName("nos_has_experience") val nosHasExperience: Map<String, Boolean>,
    val because: List<String>,
    @SerialName("gap_nos") val gapNos: List<String>,
    @SerialName("applicable_tasks") val applicableTasks: List<ApplicableTask>,
    @SerialName("rules_version") val rulesVersion: String,
)

/** Thrown for malformed declarations: unknown item ids, unsupported claim strengths,
 * duplicate ids in list-keyed input, or wrong value types. Mirrors matcher.py's
 * ValueError exactly -- same situations, equivalent messages. */
class DeclarationValidationException(message: String) : IllegalArgumentException(message)
