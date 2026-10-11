package `in`.kaushalpramaan.core.budget

import kotlin.random.Random
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BudgetLedgerTest {

    private val fiveTaskBudgets = listOf(
        TaskBudget("T1", 15_728_640L),
        TaskBudget("T2", 20_971_520L),
        TaskBudget("T3", 31_457_280L),
        TaskBudget("T4", 26_214_400L),
        TaskBudget("T5", 31_457_280L),
    )
    private val total120Mb = 125_829_120L
    private val ledger = BudgetLedger(fiveTaskBudgets, total120Mb)

    // ---- usage() recomputes purely from the item list ----

    @Test
    fun usage_sums_only_the_items_present_and_ignores_nothing_else() {
        val items = listOf(
            LedgerItem("e1", "T1", 1_000L),
            LedgerItem("e2", "T1", 2_000L),
            LedgerItem("e3", "T2", 5_000L),
        )
        val usage = ledger.usage(items)
        assertEquals(3_000L, usage.perTask.getValue("T1").usedBytes)
        assertEquals(5_000L, usage.perTask.getValue("T2").usedBytes)
        assertEquals(0L, usage.perTask.getValue("T3").usedBytes)
        assertEquals(8_000L, usage.totalUsedBytes)
        assertTrue(usage.isValid())
    }

    @Test
    fun usage_detects_an_over_budget_task_and_an_over_budget_total_independently() {
        val overTask = ledger.usage(listOf(LedgerItem("e1", "T1", fiveTaskBudgets[0].budgetBytes + 1)))
        assertTrue(overTask.perTask.getValue("T1").overBudget)
        assertFalse(overTask.isValid())

        val syntheticTightTotal = BudgetLedger(listOf(TaskBudget("T1", 10_000L), TaskBudget("T2", 10_000L)), totalBudgetBytes = 15_000L)
        val overTotal = syntheticTightTotal.usage(listOf(LedgerItem("e1", "T1", 8_000L), LedgerItem("e2", "T2", 8_000L)))
        assertFalse(overTotal.perTask.getValue("T1").overBudget)
        assertFalse(overTotal.perTask.getValue("T2").overBudget)
        assertTrue(overTotal.totalOverBudget)
        assertFalse(overTotal.isValid())
    }

    // ---- allowedBytesFor() / canAccept() ----

    @Test
    fun allowedBytesFor_is_the_smaller_of_task_remaining_and_total_remaining() {
        val items = listOf(LedgerItem("e1", "T1", 15_000_000L)) // T1 nearly full; total has plenty of room
        val allowed = ledger.allowedBytesFor(items, "T1")
        assertEquals(fiveTaskBudgets[0].budgetBytes - 15_000_000L, allowed)
    }

    @Test
    fun allowedBytesFor_credits_back_the_replaced_items_own_bytes() {
        val items = listOf(LedgerItem("old", "T1", fiveTaskBudgets[0].budgetBytes))
        val allowedWithoutCredit = ledger.allowedBytesFor(items, "T1")
        assertEquals(0L, allowedWithoutCredit)
        val allowedWithCredit = ledger.allowedBytesFor(items, "T1", replacingEvidenceId = "old")
        assertEquals(fiveTaskBudgets[0].budgetBytes, allowedWithCredit)
    }

    @Test
    fun canAccept_rejects_task_budget_before_checking_total_budget() {
        val items = listOf(LedgerItem("e1", "T1", fiveTaskBudgets[0].budgetBytes))
        val decision = ledger.canAccept(items, "T1", candidateBytes = 1L)
        assertTrue(decision is AcceptDecision.RejectedTaskBudget)
        assertEquals(0L, (decision as AcceptDecision.RejectedTaskBudget).remainingBytes)
    }

    @Test
    fun canAccept_rejects_total_budget_when_the_single_task_still_has_room() {
        val tight = BudgetLedger(listOf(TaskBudget("T1", 10_000_000L), TaskBudget("T2", 10_000_000L)), totalBudgetBytes = 8_000_000L)
        val items = listOf(LedgerItem("e1", "T2", 8_000_000L))
        val decision = tight.canAccept(items, "T1", candidateBytes = 1L)
        assertTrue(decision is AcceptDecision.RejectedTotalBudget)
    }

    @Test
    fun canAccept_accepts_exactly_at_the_remaining_boundary() {
        val items = emptyList<LedgerItem>()
        val decision = ledger.canAccept(items, "T1", candidateBytes = fiveTaskBudgets[0].budgetBytes)
        assertEquals(AcceptDecision.Accepted, decision)
    }

    // ---- fitDecision(): the automatic-optimisation three-way decision ----

    @Test
    fun fitDecision_is_FitsAsIs_when_the_raw_capture_already_fits() {
        val decision = ledger.fitDecision(emptyList(), "T1", rawBytes = 1_000_000L, qualityFloorBytes = 500_000L)
        assertEquals(FitDecision.FitsAsIs, decision)
    }

    @Test
    fun fitDecision_is_NeedsOptimization_when_raw_is_too_big_but_the_floor_fits() {
        val items = listOf(LedgerItem("e1", "T1", fiveTaskBudgets[0].budgetBytes - 1_000_000L))
        val decision = ledger.fitDecision(items, "T1", rawBytes = 5_000_000L, qualityFloorBytes = 500_000L)
        assertTrue(decision is FitDecision.NeedsOptimization)
        assertEquals(1_000_000L, (decision as FitDecision.NeedsOptimization).targetBytes)
    }

    @Test
    fun fitDecision_is_CannotFit_when_even_the_quality_floor_does_not_fit() {
        val items = listOf(LedgerItem("e1", "T1", fiveTaskBudgets[0].budgetBytes - 10L))
        val decision = ledger.fitDecision(items, "T1", rawBytes = 5_000_000L, qualityFloorBytes = 500_000L)
        assertTrue(decision is FitDecision.CannotFit)
        assertEquals(10L, (decision as FitDecision.CannotFit).remainingBytes)
    }

    // ---- the 500-randomized-operation invariant stress test ----
    //
    // Models the real caller discipline this ledger is designed for: before an add/replace is
    // actually committed to the "database" (here, a plain Map standing in for Room rows), the
    // caller must have gotten AcceptDecision.Accepted / a fitDecision target it then met. The
    // test harness enforces exactly that discipline (same as EvidenceRepository/the P5
    // optimisation pipeline will in production) and then asserts, after EVERY single
    // operation, that usage() is still valid -- proving the ledger can never be driven into an
    // over-budget state by any sequence of add/replace/delete/recompute-after-crash operations
    // when used as designed.

    private enum class Op { ADD, REPLACE, DELETE, RECOMPUTE_NOOP }

    @Test
    fun five_hundred_randomized_operations_never_violate_task_or_total_budget_invariants() {
        val random = Random(1_234_567L)
        val taskIds = fiveTaskBudgets.map { it.taskId }
        val db = LinkedHashMap<String, LedgerItem>()
        var nextId = 0

        var accepted = 0
        var rejected = 0
        var replaced = 0
        var deleted = 0

        repeat(500) { opIndex ->
            when (Op.entries[random.nextInt(Op.entries.size)]) {
                Op.ADD -> {
                    val taskId = taskIds[random.nextInt(taskIds.size)]
                    // Deliberately spans from tiny to deliberately-oversized relative to any
                    // single task's budget, so both acceptance and rejection paths fire often.
                    val candidateBytes = random.nextLong(0L, 20_000_000L)
                    val currentItems = db.values.toList()
                    when (val decision = ledger.canAccept(currentItems, taskId, candidateBytes)) {
                        AcceptDecision.Accepted -> {
                            val id = "e${nextId++}"
                            db[id] = LedgerItem(id, taskId, candidateBytes)
                            accepted++
                        }
                        is AcceptDecision.RejectedTaskBudget, is AcceptDecision.RejectedTotalBudget -> {
                            rejected++
                            // A caller discipline bug here is exactly what this test would
                            // catch: committing the item anyway would corrupt the ledger.
                            assertTrue(
                                "a rejected add must never find room via some other accounting",
                                candidateBytes > ledger.allowedBytesFor(currentItems, taskId),
                            )
                        }
                    }
                }
                Op.REPLACE -> {
                    if (db.isEmpty()) return@repeat
                    val oldId = db.keys.elementAt(random.nextInt(db.size))
                    val old = db.getValue(oldId)
                    val newBytes = random.nextLong(0L, 20_000_000L)
                    val currentItems = db.values.toList()
                    val decision = ledger.canAccept(currentItems, old.taskId, newBytes, replacingEvidenceId = oldId)
                    if (decision == AcceptDecision.Accepted) {
                        // Old item stays valid until the new one is ready, then is removed --
                        // modelled here as an atomic swap since this test only exercises the
                        // pure ledger arithmetic, not the crash-recovery state machine (that
                        // is EvidenceRepositoryTest's job, one layer up).
                        val newId = "e${nextId++}"
                        db.remove(oldId)
                        db[newId] = LedgerItem(newId, old.taskId, newBytes)
                        replaced++
                    } else {
                        rejected++
                        // Rejected replacement: the old item must still be exactly as it was.
                        assertEquals(old, db[oldId])
                    }
                }
                Op.DELETE -> {
                    if (db.isEmpty()) return@repeat
                    val id = db.keys.elementAt(random.nextInt(db.size))
                    db.remove(id)
                    deleted++
                }
                Op.RECOMPUTE_NOOP -> {
                    // Simulates process-death recovery: nothing changes, usage() is just
                    // recomputed fresh from the same source-of-truth list again.
                }
            }

            val usage = ledger.usage(db.values.toList())
            assertTrue(
                "invariant violated after operation #$opIndex (accepted=$accepted rejected=$rejected " +
                    "replaced=$replaced deleted=$deleted): $usage",
                usage.isValid(),
            )
            for (taskUsage in usage.perTask.values) {
                assertTrue(
                    "task ${taskUsage.taskId} usage ${taskUsage.usedBytes} exceeded its budget " +
                        "${taskUsage.budgetBytes} after operation #$opIndex",
                    taskUsage.usedBytes <= taskUsage.budgetBytes,
                )
            }
            assertTrue(
                "total usage ${usage.totalUsedBytes} exceeded the total budget ${usage.totalBudgetBytes} " +
                    "after operation #$opIndex",
                usage.totalUsedBytes <= usage.totalBudgetBytes,
            )
        }

        // Sanity: the random mix actually exercised both the accept and reject paths, and
        // both replace and delete -- a test that only ever hit one branch would not be
        // proving much.
        assertTrue("expected at least some accepted adds/replaces, got $accepted", accepted > 50)
        assertTrue("expected at least some rejections, got $rejected", rejected > 20)
        assertTrue("expected at least some replacements, got $replaced", replaced > 10)
        assertTrue("expected at least some deletes, got $deleted", deleted > 10)
    }

    @Test
    fun five_hundred_randomized_operations_never_leave_a_duplicate_or_dangling_evidence_id() {
        // A second randomized run, seeded differently, focused on structural corruption
        // rather than byte-budget invariants: no evidenceId ever appears twice in the
        // resulting usage, and every id referenced by a TaskUsage sum traces back to a real
        // item that is still in the "database".
        val random = Random(9_876_543L)
        val taskIds = fiveTaskBudgets.map { it.taskId }
        val db = LinkedHashMap<String, LedgerItem>()
        var nextId = 0

        repeat(500) {
            when (random.nextInt(3)) {
                0 -> {
                    val taskId = taskIds[random.nextInt(taskIds.size)]
                    val bytes = random.nextLong(0L, 5_000_000L)
                    if (ledger.canAccept(db.values.toList(), taskId, bytes) == AcceptDecision.Accepted) {
                        val id = "e${nextId++}"
                        db[id] = LedgerItem(id, taskId, bytes)
                    }
                }
                1 -> if (db.isNotEmpty()) {
                    val oldId = db.keys.elementAt(random.nextInt(db.size))
                    val old = db.getValue(oldId)
                    val bytes = random.nextLong(0L, 5_000_000L)
                    if (ledger.canAccept(db.values.toList(), old.taskId, bytes, oldId) == AcceptDecision.Accepted) {
                        val newId = "e${nextId++}"
                        db.remove(oldId)
                        db[newId] = LedgerItem(newId, old.taskId, bytes)
                    }
                }
                else -> if (db.isNotEmpty()) db.remove(db.keys.elementAt(random.nextInt(db.size)))
            }

            val ids = db.values.map { it.evidenceId }
            assertEquals("duplicate evidenceId found in the simulated ledger state", ids.size, ids.toSet().size)
            val usage = ledger.usage(db.values.toList())
            assertEquals(db.values.sumOf { it.bytes }, usage.totalUsedBytes)
        }
    }
}
