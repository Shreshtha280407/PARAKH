package `in`.kaushalpramaan.core.mapping

import java.math.BigDecimal
import java.math.RoundingMode
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonPrimitive

/**
 * Deterministic, rule-based CON/Q0602 declaration matcher (match-rules@r2) --
 * the Kotlin port of ml/mapping/matcher.py. This file must agree with that
 * one on every golden vector in ml/mapping/golden_vectors.jsonl (see
 * GoldenVectorsTest and docs/gates/Q1.md / docs/gates/P3.md). Pure Kotlin
 * stdlib + kotlinx.serialization for JSON -- no model weights, no network.
 *
 * The matcher never decides competence. It only explains how a
 * self-declaration relates to CON/Q0602 and which tasks need the most
 * evidence.
 */
object Matcher {

    /** Correctly-rounded-to-N-decimal-places double, matching CPython's round()
     * (round-half-to-even on the exact binary value of the double) exactly --
     * not Kotlin/Java's usual round-half-up string formatting. Required for
     * byte-for-byte golden-vector parity with ml/mapping/matcher.py. */
    private fun pyRound(x: Double, decimals: Int): Double =
        BigDecimal(x).setScale(decimals, RoundingMode.HALF_EVEN).toDouble()

    /** Matches Python's f"{x:.2f}" formatting exactly (same correctly-rounded
     * decimal conversion CPython's round()/format() share). */
    private fun pyFormat2f(x: Double): String =
        BigDecimal(x).setScale(2, RoundingMode.HALF_EVEN).toPlainString()

    /** Neumaier (improved Kahan) compensated summation -- matches
     * ml/mapping/matcher.py's _compensated_sum() exactly. CPython's builtin
     * sum() has used compensated summation for float addition since 3.12,
     * which is more accurate than Kotlin stdlib's naive
     * Iterable<Double>.sum() (plain sequential `total += v`) -- accurate
     * enough that the two can land one ULP apart on identical inputs, which
     * is enough to flip a value sitting exactly on a rounding boundary (the
     * real bug this fixes: 0.225*3/12 = 0.05625 rounded to 0.0562 in Kotlin
     * vs 0.0563 in Python; see docs/gates/Q1.md). Using the SAME explicit
     * algorithm in both languages makes the result depend on our own
     * auditable code, not a Python-version-specific stdlib internal. */
    private fun compensatedSum(values: List<Double>): Double {
        var total = 0.0
        var c = 0.0
        for (v in values) {
            val t = total + v
            c += if (Math.abs(total) >= Math.abs(v)) (total - t) + v else (v - t) + total
            total = t
        }
        return total + c
    }

    private fun describeType(e: JsonElement?): String = when (e) {
        null, is JsonNull -> "NoneType"
        is JsonObject -> "dict"
        is JsonArray -> "list"
        is JsonPrimitive -> if (e.isString) "str" else "number/bool"
    }

    /** Accepts either the canonical dict form
     * {"answers": {item_id: "often"|"sometimes"|"never", ...}, "free_text": "..."}
     * or the list-keyed form
     * {"answers": [{"item_id": ..., "answer": ...}, ...], "free_text": "..."}.
     * Raises DeclarationValidationException with a specific message on any
     * malformed shape -- mirrors matcher.py's normalize_declaration(). */
    fun normalizeDeclaration(raw: JsonElement): Declaration {
        if (raw !is JsonObject) {
            throw DeclarationValidationException("declaration must be an object, got ${describeType(raw)}")
        }
        val answers = linkedMapOf<String, String>()
        when (val answersElement = raw["answers"]) {
            null, is JsonNull -> {}
            is JsonArray -> {
                val seen = mutableSetOf<String>()
                answersElement.forEachIndexed { i, rec ->
                    if (rec !is JsonObject || rec["item_id"] == null || rec["answer"] == null) {
                        throw DeclarationValidationException(
                            "declaration['answers'][$i] must be an object with 'item_id' and 'answer' keys, got $rec"
                        )
                    }
                    val itemId = rec.getValue("item_id").jsonPrimitive.content
                    val answer = rec.getValue("answer").jsonPrimitive.content
                    if (itemId in seen) {
                        throw DeclarationValidationException("duplicate declaration item_id in answers list: '$itemId'")
                    }
                    seen += itemId
                    answers[itemId] = answer
                }
            }
            is JsonObject -> {
                for ((k, v) in answersElement) {
                    answers[k] = v.jsonPrimitive.content
                }
            }
            else -> throw DeclarationValidationException(
                "declaration['answers'] must be an object or a list, got ${describeType(answersElement)}"
            )
        }
        val freeTextElement = raw["free_text"]
        val freeText = when {
            freeTextElement == null || freeTextElement is JsonNull -> ""
            freeTextElement is JsonPrimitive && freeTextElement.isString -> freeTextElement.content
            else -> throw DeclarationValidationException(
                "declaration['free_text'] must be a string, got ${describeType(freeTextElement)}"
            )
        }
        return Declaration(answers = answers, freeText = freeText)
    }

    /** Validates a *normalized* declaration's values against the pinned rules.
     * Mirrors matcher.py's validate_declaration() -- unknown item ids and
     * unsupported claim-strength values both raise, naming every offender. */
    fun validateDeclaration(declaration: Declaration, rules: Rules) {
        val knownIds = (rules.links.cards.map { it.id } + rules.links.tools.map { it.id }).toSet()
        val validAnswers = rules.thresholds.answerStrength.keys

        val unknown = declaration.answers.keys.filter { it !in knownIds }.sorted()
        if (unknown.isNotEmpty()) {
            throw DeclarationValidationException(
                "unknown declaration item id(s): ${unknown.joinToString(", ")} " +
                    "(not a card or tool defined in mapping/links.json)"
            )
        }

        val badValues = declaration.answers.entries
            .filter { it.value !in validAnswers }
            .map { "${it.key}='${it.value}'" }
            .sorted()
        if (badValues.isNotEmpty()) {
            throw DeclarationValidationException(
                "unsupported claim strength for: ${badValues.joinToString(", ")} " +
                    "(must be one of ${validAnswers.sorted()})"
            )
        }
    }

    private fun keywordHit(keywords: KeywordsFile, itemId: String, freeText: String): Boolean {
        if (freeText.isEmpty()) return false
        val entry = keywords.cards[itemId] ?: return false
        val text = freeText.lowercase()
        for (terms in entry.values) {
            for (term in terms) {
                if (text.contains(term.lowercase())) return true
            }
        }
        return false
    }

    private fun declarationItems(rules: Rules): List<DeclarationItem> = rules.links.cards + rules.links.tools

    /** Core match, already-normalized/validated input. */
    fun match(declaration: Declaration, rules: Rules): MatchOutput {
        validateDeclaration(declaration, rules)

        val thresholds = rules.thresholds
        val answerStrength = thresholds.answerStrength
        val answers = declaration.answers
        val freeText = declaration.freeText

        val pcClaim = linkedMapOf<String, Double>()
        val pcSources = linkedMapOf<String, MutableList<String>>()

        for (item in declarationItems(rules)) {
            var base = answerStrength[answers[item.id] ?: "never"] ?: 0.0
            if (base < 0.6 && keywordHit(rules.keywords, item.id, freeText)) {
                base = maxOf(base, 0.6)
            }
            if (base <= 0.0) continue
            for (link in item.links) {
                val fullPc = "${link.nos}.${link.pc}"
                val contribution = base * link.weight
                val current = pcClaim[fullPc] ?: 0.0
                when {
                    contribution > current -> {
                        pcClaim[fullPc] = contribution
                        pcSources[fullPc] = mutableListOf(item.id)
                    }
                    contribution == current -> {
                        pcSources.getOrPut(fullPc) { mutableListOf() }.add(item.id)
                    }
                }
            }
        }

        val nosPcs = linkedMapOf<String, MutableSet<String>>()
        for (item in declarationItems(rules)) {
            for (link in item.links) {
                nosPcs.getOrPut(link.nos) { mutableSetOf() }.add(link.pc)
            }
        }

        val nosCoverageRaw = linkedMapOf<String, Double>()
        val nosExperience = linkedMapOf<String, Boolean>()
        for (entry in thresholds.practicalNosForMatching) {
            val nos = entry.nos
            // sorted(): matches ml/mapping/matcher.py exactly -- floating-point sum()
            // is not associative, so claims must be summed in the same (sorted, not
            // hash- or insertion-order-dependent) sequence in both languages for
            // identical results at every rounding boundary. See matcher.py's comment
            // on this same line for the full rationale.
            val pcs = (nosPcs[nos] ?: emptySet()).sorted()
            val claims = pcs.map { pcClaim["$nos.$it"] ?: 0.0 }
            val coverage = if (claims.isNotEmpty()) compensatedSum(claims) / claims.size else 0.0
            nosCoverageRaw[nos] = coverage
            nosExperience[nos] = claims.any { it > 0.0 }
        }

        val totalCredits = thresholds.practicalNosForMatching.sumOf { it.credits } // ints, exact
        val overallRaw = compensatedSum(
            thresholds.practicalNosForMatching.map { (nosCoverageRaw[it.nos] ?: 0.0) * it.credits },
        ) / totalCredits

        val allHaveExperience = nosExperience.values.all { it }
        val matchResult = when {
            overallRaw >= 0.60 && allHaveExperience -> "appropriate_match"
            overallRaw >= 0.35 -> "partial_match"
            else -> "not_appropriate_match"
        }

        val gapNos = nosCoverageRaw.filter { (nos, cov) -> cov < 0.60 || nosExperience[nos] != true }.keys.toList()

        val because = thresholds.practicalNosForMatching.map { entry ->
            val nos = entry.nos
            if (nosExperience[nos] != true) {
                "$nos: no declared experience on any linked card/tool"
            } else {
                "$nos: coverage ${pyFormat2f(nosCoverageRaw[nos] ?: 0.0)} from ${entry.credits} credits"
            }
        }

        val applicableTasks = thresholds.practicalNosForMatching.map { entry ->
            val nos = entry.nos
            ApplicableTask(task = rules.nosTask[nos], nos = nos, extraEvidenceNeeded = nos in gapNos)
        }

        val declarationOnlySignals = thresholds.declarationOnlyNos.map { entry ->
            val nos = entry.nos
            val pcs = nosPcs[nos] ?: emptySet()
            val matchedItems = sortedSetOf<String>()
            var hasExperience = false
            for (pc in pcs) {
                val fullPc = "$nos.$pc"
                if ((pcClaim[fullPc] ?: 0.0) > 0.0) {
                    hasExperience = true
                    pcSources[fullPc]?.let { matchedItems.addAll(it) }
                }
            }
            val label = entry.label
            val becauseLine = if (hasExperience) {
                "$nos ($label): worker declared relevant experience — informational only, not scored"
            } else {
                "$nos ($label): no declared experience — informational only, not scored"
            }
            DeclarationOnlySignal(
                nos = nos,
                label = label,
                hasDeclaredExperience = hasExperience,
                matchedItems = matchedItems.toList(),
                because = becauseLine,
            )
        }

        return MatchOutput(
            matchResult = matchResult,
            overallCoverage = pyRound(overallRaw, 4),
            nosCoverage = nosCoverageRaw.mapValues { (_, c) -> pyRound(c, 4) },
            nosHasExperience = nosExperience,
            because = because,
            gapNos = gapNos,
            applicableTasks = applicableTasks,
            declarationOnlySignals = declarationOnlySignals,
            rulesVersion = thresholds.matchRulesId,
        )
    }

    /** Convenience entry point matching Python's single flexible match() --
     * accepts a raw JsonElement (dict or list-keyed answers form), normalizes
     * and validates it, then computes the result. */
    fun match(raw: JsonElement, rules: Rules): MatchOutput = match(normalizeDeclaration(raw), rules)

    /** Convenience entry point for Compose UI code that already has a typed
     * Map<String,String> of answers (the common case) -- skips JSON boxing. */
    fun match(answers: Map<String, String>, freeText: String, rules: Rules): MatchOutput =
        match(Declaration(answers = answers, freeText = freeText), rules)
}
