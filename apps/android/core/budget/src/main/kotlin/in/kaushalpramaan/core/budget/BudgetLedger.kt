package `in`.kaushalpramaan.core.budget

/**
 * Pure, deterministic, exhaustively-tested final-evidence budget ledger (P5 spec part B).
 *
 * Every function here RECOMPUTES from the [items] list passed in -- the actual source of
 * truth (Room rows, in production) -- rather than trusting any cached/incremental count. That
 * is the whole safety property: callers never need to "remember" to keep a running total in
 * sync, because there is no running total to go stale. The same function, called again after
 * an add/delete/replace/trim/optimisation-completion/process-death-recovery, always recomputes
 * the exact right answer from whatever [items] now looks like -- there is no other state this
 * class holds.
 */
class BudgetLedger(private val taskBudgets: List<TaskBudget>, private val totalBudgetBytes: Long) {

    private val budgetByTask: Map<String, Long> = taskBudgets.associate { it.taskId to it.budgetBytes }

    /** Recomputes current usage for every configured task plus the assessment total, purely
     * from [items]. [items] should contain exactly the current final (READY) evidence set --
     * nothing more (no STAGING/DELETED rows), nothing less. */
    fun usage(items: List<LedgerItem>): LedgerUsage {
        val usedByTask = items.groupBy { it.taskId }.mapValues { (_, v) -> v.sumOf { it.bytes } }
        val perTask = budgetByTask.mapValues { (taskId, budget) ->
            TaskUsage(taskId = taskId, usedBytes = usedByTask[taskId] ?: 0L, budgetBytes = budget)
        }
        val totalUsed = items.sumOf { it.bytes }
        return LedgerUsage(perTask = perTask, totalUsedBytes = totalUsed, totalBudgetBytes = totalBudgetBytes)
    }

    /** The exact allowed final byte limit for one capture/optimisation pass: the smaller of
     * the task's remaining budget and the assessment's remaining total budget, with
     * [replacingEvidenceId]'s own bytes credited back first when this is a replacement (the
     * old item stays valid and counted until the new one is actually ready -- that state
     * machine lives one level up in the caller; this is purely the arithmetic). */
    fun allowedBytesFor(items: List<LedgerItem>, candidateTaskId: String, replacingEvidenceId: String? = null): Long {
        val before = usage(effectiveItems(items, replacingEvidenceId))
        val taskUsage = before.perTask[candidateTaskId]
        val taskRemaining = ((taskUsage?.budgetBytes ?: 0L) - (taskUsage?.usedBytes ?: 0L)).coerceAtLeast(0L)
        return minOf(taskRemaining, before.totalRemainingBytes)
    }

    /** Would accepting a final item of [candidateBytes] bytes into [candidateTaskId] keep
     * every invariant intact against the current [items] snapshot? */
    fun canAccept(
        items: List<LedgerItem>,
        candidateTaskId: String,
        candidateBytes: Long,
        replacingEvidenceId: String? = null,
    ): AcceptDecision {
        val effective = effectiveItems(items, replacingEvidenceId)
        val before = usage(effective)
        val taskUsage = before.perTask[candidateTaskId]
        val taskBudget = taskUsage?.budgetBytes ?: 0L
        val taskUsed = taskUsage?.usedBytes ?: 0L
        val taskRemaining = (taskBudget - taskUsed).coerceAtLeast(0L)
        if (candidateBytes > taskRemaining) return AcceptDecision.RejectedTaskBudget(taskRemaining)
        val totalRemaining = before.totalRemainingBytes
        if (candidateBytes > totalRemaining) return AcceptDecision.RejectedTotalBudget(totalRemaining)
        return AcceptDecision.Accepted
    }

    /** The automatic-optimisation decision P5's photo/video optimisers ask for before doing
     * any real work: given the as-captured [rawBytes] and the [qualityFloorBytes] the
     * optimiser can realistically reach for this media kind, does it already fit as-is, does
     * it need an optimisation pass (and to what target), or is it impossible to fit even at
     * the floor? */
    fun fitDecision(
        items: List<LedgerItem>,
        candidateTaskId: String,
        rawBytes: Long,
        qualityFloorBytes: Long,
        replacingEvidenceId: String? = null,
    ): FitDecision {
        val allowed = allowedBytesFor(items, candidateTaskId, replacingEvidenceId)
        return when {
            rawBytes <= allowed -> FitDecision.FitsAsIs
            qualityFloorBytes <= allowed -> FitDecision.NeedsOptimization(allowed)
            else -> FitDecision.CannotFit(allowed)
        }
    }

    private fun effectiveItems(items: List<LedgerItem>, replacingEvidenceId: String?): List<LedgerItem> =
        if (replacingEvidenceId != null) items.filterNot { it.evidenceId == replacingEvidenceId } else items
}
