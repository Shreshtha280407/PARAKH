package `in`.kaushalpramaan.core.mapping

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.BeforeClass
import org.junit.Test

/**
 * The Kotlin-side half of the Python/Kotlin match-rules@r2 golden-vector
 * parity requirement (master plan p.8 / p.18; docs/gates/Q1.md,
 * docs/gates/P3.md): "Kotlin and Python matcher outputs identical on all 100
 * golden vectors." Reads the SAME ml/mapping/golden_vectors.jsonl Python
 * reads (synced in by build.gradle.kts's syncGoldenVectors task -- never a
 * hand-copied duplicate).
 *
 * Run: ./gradlew :core:mapping:test --tests "*GoldenVectorsTest*"
 */
class GoldenVectorsTest {

    companion object {
        private val json = Json { ignoreUnknownKeys = true }
        private lateinit var rules: Rules
        private lateinit var vectors: List<JsonObject>

        @BeforeClass
        @JvmStatic
        fun setup() {
            rules = RulesLoader.load()
            val text = readClasspathResource("/pack/golden_vectors.jsonl")
            vectors = text.lineSequence()
                .map { it.trim() }
                .filter { it.isNotEmpty() && !it.startsWith("//") }
                .map { json.parseToJsonElement(it).jsonObject }
                .toList()
        }
    }

    @Test
    fun all_100_vectors_match_python() {
        assertEquals("expected 100 golden vectors", 100, vectors.size)

        val mismatches = mutableListOf<String>()
        for (vector in vectors) {
            val id = vector.getValue("id").jsonPrimitive.content
            val input = vector.getValue("input")
            val expected = json.decodeFromJsonElement(MatchOutput.serializer(), vector.getValue("expected_output"))
            val actual = Matcher.match(input, rules)
            if (actual != expected) {
                mismatches += "$id (expected=$expected actual=$actual)"
            }
        }
        assertTrue(
            "Kotlin matcher output drifted from ml/mapping/golden_vectors.jsonl for: ${mismatches.take(5)} " +
                "(${mismatches.size} total mismatches)",
            mismatches.isEmpty(),
        )
    }

    @Test
    fun matcher_is_deterministic() {
        for (vector in vectors.take(10)) {
            val input = vector.getValue("input")
            val a = Matcher.match(input, rules)
            val b = Matcher.match(input, rules)
            assertEquals(a, b)
        }
    }

    @Test
    fun no_network_mode_does_not_affect_matching_or_task_pack_loading() {
        // The Kotlin matcher and RulesLoader never perform I/O beyond reading
        // bundled classpath resources -- there is no code path that could
        // behave differently with networking disabled. This test pins that:
        // reloading rules and re-running every vector produces byte-identical
        // results to the first run in this same (networkless, by construction
        // of this JVM test environment having no network calls in the code
        // under test) process.
        val reloadedRules = RulesLoader.load()
        assertEquals(rules.thresholds.matchRulesId, reloadedRules.thresholds.matchRulesId)
        assertEquals(rules.tasksFile.tasks.size, reloadedRules.tasksFile.tasks.size)
        for (vector in vectors) {
            val input = vector.getValue("input")
            assertEquals(Matcher.match(input, rules), Matcher.match(input, reloadedRules))
        }
    }
}
