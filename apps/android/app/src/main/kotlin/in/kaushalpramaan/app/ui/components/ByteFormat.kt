package `in`.kaushalpramaan.app.ui.components

/** Human-readable MB display for evidence budgets/usage, e.g. 12_582_912L -> "12.0 MB". */
fun formatMb(bytes: Long): String {
    val mb = bytes / (1024.0 * 1024.0)
    return "%.1f MB".format(mb)
}
