package `in`.kaushalpramaan.app

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.uiautomator.UiDevice
import org.junit.After
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * P-3 exit test: "The app remains usable with network disabled." Flips the
 * emulator into airplane mode via a shell command (matching the master
 * plan's own `adb shell cmd connectivity airplane-mode enable` check) and
 * drives a normal navigation sequence while it is on, then restores it.
 * Combined with NetworkAssertions (no INTERNET permission at all) and
 * app/build.gradle.kts's verifyNoNetworkDependencies, this is the runtime
 * half of "no network is possible, and the app doesn't need it anyway."
 */
@RunWith(AndroidJUnit4::class)
class OfflineAirplaneModeTest {

    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    private val device: UiDevice = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())

    @Before
    fun enableAirplaneMode() {
        device.executeShellCommand("cmd connectivity airplane-mode enable")
    }

    @After
    fun disableAirplaneMode() {
        device.executeShellCommand("cmd connectivity airplane-mode disable")
    }

    @Test
    fun app_completes_match_with_airplane_mode_on() {
        NetworkAssertions.assertAppHasNoInternetCapability(composeRule.activity)

        composeRule.completeIntake(languageTag = "en")
        composeRule.answerAllDeclarationItems("often")

        composeRule.onNodeWithText("Appropriate match").assertIsDisplayed()
        composeRule.tapTag("btn_view_tasks")
        composeRule.onNodeWithText("Practice tasks").assertIsDisplayed()
    }
}
