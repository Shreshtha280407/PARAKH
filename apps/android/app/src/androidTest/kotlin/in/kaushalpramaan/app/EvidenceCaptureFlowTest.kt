package `in`.kaushalpramaan.app

import android.Manifest
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.waitUntilExactlyOneExists
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Drives one real CameraX photo capture through the app's actual UI on real camera
 * hardware -- no mock evidence, no fake byte sizes (that era ended with P3; see
 * docs/gates/P3.md's "Limits, stated honestly"). Exact budget-boundary behaviour (fill a
 * task's budget to the exact byte, assert overflow rejection) is covered precisely at the
 * unit level in EvidenceRepositoryTest, since a real photo's byte size can't be dialled to
 * an exact number the way the old mock slider could -- this test instead proves the real
 * add -> replace -> remove roundtrip actually works end to end against the real camera,
 * real file system, and real SQLCipher-encrypted database.
 */
@RunWith(AndroidJUnit4::class)
class EvidenceCaptureFlowTest {

    @get:Rule(order = 0)
    val clearDraftRule = ClearP4DraftBeforeTest()

    @get:Rule(order = 1)
    val permissionRule = GrantPermissionsViaShell(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO)

    @get:Rule(order = 2)
    val composeRule = createAndroidComposeRule<MainActivity>()

    @OptIn(ExperimentalTestApi::class)
    @Test
    fun real_photo_capture_add_replace_remove_roundtrip() {
        composeRule.completeIntake(languageTag = "en")
        composeRule.tapTag("btn_see_match")
        composeRule.tapTag("btn_view_tasks")
        composeRule.tapTag("task_card_T1")

        // Add: real capture, real file, real DB write.
        composeRule.tapTag("btn_add_evidence")
        composeRule.waitUntilExactlyOneExists(hasTestTag("btn_capture_shutter"), timeoutMillis = 15_000)
        composeRule.tapTag("btn_capture_shutter")
        composeRule.waitUntilExactlyOneExists(hasTestTag("btn_add_evidence"), timeoutMillis = 15_000)
        composeRule.onAllNodesWithTag("evidence_row").assertCountEquals(1)

        // Replace: a second real capture must swap in for the first, never duplicate it.
        composeRule.tapTag("btn_replace_evidence_0")
        composeRule.waitUntilExactlyOneExists(hasTestTag("btn_capture_shutter"), timeoutMillis = 15_000)
        composeRule.tapTag("btn_capture_shutter")
        composeRule.waitUntilExactlyOneExists(hasTestTag("btn_add_evidence"), timeoutMillis = 15_000)
        composeRule.onAllNodesWithTag("evidence_row").assertCountEquals(1)

        // Remove: destructive-delete confirmation, then the task goes back to empty.
        composeRule.tapTag("btn_remove_evidence_0")
        composeRule.tapTag("btn_confirm_remove_evidence")
        composeRule.onNodeWithText("No evidence added yet.").assertIsDisplayed()
    }
}
