package `in`.kaushalpramaan.core.budget

/** One task's configured final-package budget. Read from the canonical pack by the caller
 * (e.g. `core:mapping`'s `Rules`) and passed in as plain data -- this module has no
 * knowledge of, and no dependency on, where budgets come from. */
data class TaskBudget(val taskId: String, val budgetBytes: Long)

/** The pure, source-of-truth shape of one final (READY) evidence item this module reasons
 * about. Deliberately minimal -- no Room/Android types leak into `core:budget`. */
data class LedgerItem(
    val evidenceId: String,
    val taskId: String,
    val bytes: Long,
)

data class TaskUsage(val taskId: String, val usedBytes: Long, val budgetBytes: Long) {
    val remainingBytes: Long get() = (budgetBytes - usedBytes).coerceAtLeast(0L)
    val overBudget: Boolean get() = usedBytes > budgetBytes
}

data class LedgerUsage(
    val perTask: Map<String, TaskUsage>,
    val totalUsedBytes: Long,
    val totalBudgetBytes: Long,
) {
    val totalRemainingBytes: Long get() = (totalBudgetBytes - totalUsedBytes).coerceAtLeast(0L)
    val totalOverBudget: Boolean get() = totalUsedBytes > totalBudgetBytes

    /** True iff no task and no total is over its configured budget -- the one invariant the
     * whole P5 ledger exists to guarantee. */
    fun isValid(): Boolean = !totalOverBudget && perTask.values.none { it.overBudget }
}

sealed class AcceptDecision {
    data object Accepted : AcceptDecision()
    data class RejectedTaskBudget(val remainingBytes: Long) : AcceptDecision()
    data class RejectedTotalBudget(val remainingBytes: Long) : AcceptDecision()
}

/** The three-way automatic-optimisation decision P5's photo/video optimisers ask this ledger
 * for before doing any real work: does the as-captured file already fit (keep byte-identical),
 * does it need an optimisation pass targeting [NeedsOptimization.targetBytes], or does even
 * the quality floor make it impossible to fit ([CannotFit] above the floor)? */
sealed class FitDecision {
    data object FitsAsIs : FitDecision()
    data class NeedsOptimization(val targetBytes: Long) : FitDecision()
    data class CannotFit(val remainingBytes: Long) : FitDecision()
}
