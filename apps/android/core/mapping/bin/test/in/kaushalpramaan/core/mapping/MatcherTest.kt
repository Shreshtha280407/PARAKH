package `in`.kaushalpramaan.core.mapping

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.BeforeClass
import org.junit.Test

/** Kotlin mirror of ml/mapping/test_matcher.py's structural/validation
 * assertions -- same situations, same expected behaviour, so a change that
 * breaks parity in either language is caught on its own side too. */
class MatcherTest {

    companion object {
        private lateinit var rules: Rules

        @BeforeClass
        @JvmStatic
        fun setup() {
            rules = RulesLoader.load()
        }
    }

    @Test
    fun all_often_is_appropriate() {
        val answers = (rules.links.cards + rules.links.tools).associate { it.id to "often" }
        val r = Matcher.match(Declaration(answers = answers), rules)
        assertEquals("appropriate_match", r.matchResult)
        assertTrue(r.overallCoverage >= 0.60)
    }

    @Test
    fun all_never_is_not_appropriate() {
        val r = Matcher.match(Declaration(), rules)
        assertEquals("not_appropriate_match", r.matchResult)
        assertEquals(0.0, r.overallCoverage, 0.0)
        assertTrue(r.nosHasExperience.values.none { it })
    }

    @Test
    fun t1_safety_appears_in_applicable_tasks() {
        val r = Matcher.match(Declaration(), rules)
        val taskIds = r.applicableTasks.map { it.task }.toSet()
        assertEquals(setOf("T1", "T2", "T3", "T4", "T5"), taskIds)
        assertTrue(r.nosCoverage.containsKey("CON/N9001"))
        val t1 = r.applicableTasks.first { it.task == "T1" }
        assertEquals("CON/N9001", t1.nos)
        assertTrue(t1.extraEvidenceNeeded)
    }

    @Test
    fun declaration_only_signals_never_move_the_score() {
        val baseline = Matcher.match(Declaration(), rules)
        val teamworkOnly = Matcher.match(
            Declaration(answers = mapOf("TM01" to "often", "TM02" to "often", "TM03" to "often", "TM04" to "often",
                "PL01" to "often", "PL02" to "often", "PL03" to "often", "PL04" to "often")),
            rules,
        )
        assertEquals(baseline.overallCoverage, teamworkOnly.overallCoverage, 0.0)
        assertEquals(baseline.matchResult, teamworkOnly.matchResult)
        assertEquals(baseline.nosCoverage, teamworkOnly.nosCoverage)
        assertEquals(baseline.gapNos, teamworkOnly.gapNos)

        val tmSignal = teamworkOnly.declarationOnlySignals.first { it.nos == "CON/N8001" }
        assertTrue(tmSignal.hasDeclaredExperience)
        val baseTmSignal = baseline.declarationOnlySignals.first { it.nos == "CON/N8001" }
        assertFalse(baseTmSignal.hasDeclaredExperience)
    }

    @Test
    fun hindi_keyword_boosts_coverage() {
        val without = Matcher.match(Declaration(answers = mapOf("C08" to "never")), rules)
        val withHindi = Matcher.match(Declaration(answers = mapOf("C08" to "never"), freeText = "मैंने अर्थिंग का काम किया"), rules)
        assertTrue(withHindi.overallCoverage > without.overallCoverage)
    }

    @Test
    fun hinglish_keyword_boosts_coverage() {
        val without = Matcher.match(Declaration(answers = mapOf("C08" to "never")), rules)
        val withHinglish = Matcher.match(Declaration(answers = mapOf("C08" to "never"), freeText = "maine earthing kiya tha"), rules)
        assertTrue(withHinglish.overallCoverage > without.overallCoverage)
    }

    @Test
    fun rejects_unknown_item_id() {
        try {
            Matcher.match(Declaration(answers = mapOf("NOT_A_REAL_CARD" to "often")), rules)
            fail("expected DeclarationValidationException for unknown item id")
        } catch (e: DeclarationValidationException) {
            assertTrue(e.message!!.contains("NOT_A_REAL_CARD"))
        }
    }

    @Test
    fun rejects_unsupported_claim_strength() {
        try {
            Matcher.match(Declaration(answers = mapOf("C01" to "always")), rules)
            fail("expected DeclarationValidationException for unsupported claim strength")
        } catch (e: DeclarationValidationException) {
            assertTrue(e.message!!.contains("C01"))
        }
    }

    @Test
    fun rejects_duplicate_id_in_list_form() {
        val raw = kotlinx.serialization.json.Json.parseToJsonElement(
            """{"answers": [{"item_id":"C01","answer":"often"},{"item_id":"C01","answer":"never"}]}""",
        )
        try {
            Matcher.match(raw, rules)
            fail("expected DeclarationValidationException for duplicate item_id")
        } catch (e: DeclarationValidationException) {
            assertTrue(e.message!!.contains("C01"))
        }
    }

    @Test
    fun list_form_normalizes_to_same_result_as_dict_form() {
        val dictForm = Matcher.match(Declaration(answers = mapOf("C01" to "often", "TL01" to "sometimes")), rules)
        val raw = kotlinx.serialization.json.Json.parseToJsonElement(
            """{"answers": [{"item_id":"C01","answer":"often"},{"item_id":"TL01","answer":"sometimes"}]}""",
        )
        val listForm = Matcher.match(raw, rules)
        assertEquals(dictForm, listForm)
    }
}
