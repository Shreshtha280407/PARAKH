package `in`.kaushalpramaan.app.data.sync

/**
 * A short, fixed, UI-safe label for why a sync attempt didn't (yet) succeed -- persisted on
 * [in.kaushalpramaan.app.data.draft.OutboxItemEntity.lastErrorCategory]. Deliberately NOT a raw
 * exception message, HTTP response body, server stack trace, file path, or capability token:
 * none of those are safe to show a worker or write to a column a crash report / support
 * screenshot might surface (P6 security rule 8). [RETRYABLE] categories are exactly the ones
 * WorkManager's own exponential backoff should retry; [TERMINAL] categories mean "this exact
 * attempt will never succeed by retrying the same bytes" -- see [SyncState.FAILED_ACTION_REQUIRED].
 */
enum class SyncErrorCategory(val retryable: Boolean) {
    NETWORK_UNAVAILABLE(retryable = true),
    TIMEOUT(retryable = true),
    SERVER_UNAVAILABLE(retryable = true),
    QUOTA_EXCEEDED(retryable = false),
    INTEGRITY_REJECTED(retryable = false),
    SIGNATURE_REJECTED(retryable = false),
    REVISION_SUPERSEDED(retryable = false),
    UNAUTHORIZED(retryable = false),
    UNKNOWN_SERVER_ERROR(retryable = true),
}
