package `in`.kaushalpramaan.app.ui

import androidx.work.WorkInfo
import `in`.kaushalpramaan.app.data.EvidenceType
import `in`.kaushalpramaan.app.data.draft.*
import `in`.kaushalpramaan.app.ui.components.*
import org.junit.Assert.*
import org.junit.Test

class SyncPresentationTest {
    private val photo = EvidenceDraftEntity("photo", "a", "T1", EvidenceType.PHOTO, "photo.jpg", 2000,
        0, 100, 100, null, EvidenceDraftState.READY, null, false, finalBytes = 1000)
    private fun row(state: SyncState, bytes: Long = 0) = OutboxItemEntity("row", "a", "rev", "key",
        OutboxItemKind.EVIDENCE, "photo", "T1", "vault/photo", 1, 0, syncState = state, bytesUploaded = bytes)
    @Test fun unsealedEvidenceDoesNotClaimToBeUploadingEvenWhenOffline() {
        assertEquals(SyncPhase.BEFORE_SEAL, syncPresentation(false, false, false, emptyList(), emptyList(), null).phase)
    }
    @Test fun offlineSealedEvidenceShowsProblemAndRetry() {
        val status = syncPresentation(true, false, false, listOf(row(SyncState.QUEUED)), listOf(photo), WorkInfo.State.FAILED)
        assertEquals(SyncPhase.OFFLINE, status.phase); assertTrue(status.problem); assertFalse(status.active)
    }
    @Test fun queuedShowsActivityWithoutInventingByteProgress() {
        val status = syncPresentation(true, false, true, emptyList(), emptyList(), WorkInfo.State.ENQUEUED)
        assertEquals(SyncPhase.QUEUED, status.phase); assertTrue(status.active); assertEquals(0f, status.fraction)
    }
    @Test fun cancelledWorkStopsActivityAndEnablesRetry() {
        val status = syncPresentation(true, false, true, emptyList(), emptyList(), WorkInfo.State.CANCELLED)
        assertEquals(SyncPhase.FAILED, status.phase); assertFalse(status.active)
    }
    @Test fun manualRetryAnimatesWhileEarlierErrorRowsAreBeingReset() {
        val status = syncPresentation(true, false, true, listOf(row(SyncState.FAILED_ACTION_REQUIRED)), listOf(photo), WorkInfo.State.RUNNING)
        assertEquals(SyncPhase.UPLOADING, status.phase); assertTrue(status.active)
    }
    @Test fun uploadProgressUsesAcknowledgedBytesAndFinalOptimizedSize() {
        val status = syncPresentation(true, false, true, listOf(row(SyncState.UPLOADING, 400)), listOf(photo), WorkInfo.State.RUNNING)
        assertEquals(SyncPhase.UPLOADING, status.phase); assertEquals(.4f, status.fraction, .001f)
        assertEquals(1000L, status.totalBytes); assertEquals(400L, status.uploadedBytes)
    }
    @Test fun verifiedItemsStillWaitForServerSubmissionBeforeSuccess() {
        val status = syncPresentation(true, false, true, listOf(row(SyncState.SYNCED)), listOf(photo), WorkInfo.State.RUNNING)
        assertEquals(SyncPhase.VERIFYING, status.phase); assertEquals(1f, status.fraction)
    }
    @Test fun failedWorkStaysFailedWhenInternetReturns() {
        val status = syncPresentation(true, false, true, listOf(row(SyncState.RETRYING)), listOf(photo), WorkInfo.State.FAILED, attempts = 1)
        assertEquals(SyncPhase.FAILED, status.phase); assertTrue(status.problem); assertFalse(status.active)
    }
    @Test fun anInactiveUploadIsFlaggedWithoutFakeProgress() {
        val status = syncPresentation(true, false, true, listOf(row(SyncState.UPLOADING, 300)), listOf(photo), WorkInfo.State.RUNNING,
            lastActivityAt = 1000, now = 61_000)
        assertEquals(SyncPhase.STALLED, status.phase); assertEquals(.3f, status.fraction, .001f)
    }
    @Test fun confirmedSubmissionRemainsSuccessfulOfflineAndAfterOutboxCleanup() {
        val status = syncPresentation(true, true, false, emptyList(), emptyList(), WorkInfo.State.SUCCEEDED)
        assertEquals(SyncPhase.SUBMITTED, status.phase); assertEquals(1f, status.fraction)
    }
    @Test fun reopenedDraftDoesNotClaimThatNewEvidenceHasAlreadyBeenSubmitted() {
        assertEquals(SyncPhase.BEFORE_SEAL, syncPresentation(false, true, true, emptyList(), emptyList(), null).phase)
    }
    @Test fun allBytesAcknowledgedStillRequiresServerConfirmation() {
        val status = syncPresentation(true, false, true, listOf(row(SyncState.UPLOADING, 1000)), listOf(photo), WorkInfo.State.RUNNING)
        assertEquals(SyncPhase.VERIFYING, status.phase)
        assertFalse(status.phase == SyncPhase.SUBMITTED)
    }
}
