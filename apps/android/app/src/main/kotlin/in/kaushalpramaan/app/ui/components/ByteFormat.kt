package `in`.kaushalpramaan.app.ui.components

/** Human-readable MB display for evidence budgets/usage, e.g. 12_582_912L -> "12.0 MB". */
fun formatMb(bytes: Long): String {
    val mb = bytes / (1024.0 * 1024.0)
    return "%.1f MB".format(mb)
}

/** Human-readable m:ss display for video duration, e.g. 7_000L -> "0:07". */
fun formatDuration(millis: Long): String {
    val totalSeconds = millis / 1000
    val minutes = totalSeconds / 60
    val seconds = totalSeconds % 60
    return "%d:%02d".format(minutes, seconds)
}
