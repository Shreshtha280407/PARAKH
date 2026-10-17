package `in`.kaushalpramaan.app

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.data.CandidateSecurity
import `in`.kaushalpramaan.app.data.draft.AppDatabase
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalTestApi::class)
class RegistrationPinFlowTest {
    @get:Rule(order = 0) val clear = ClearP4DraftBeforeTest()
    @get:Rule(order = 1) val compose = createAndroidComposeRule<MainActivity>()

    @Test fun offlineRegistrationNamePersistenceAndResumeRequirePin() {
        check(compose.activity.packageName.endsWith(".p8validation"))
        val vm = ViewModelProvider(compose.activity)[AppViewModel::class.java]
        compose.completeIntake(languageTag = "en", phone = "9876543210", pin = "1847")
        compose.runOnIdle { vm.startOrResumeAssessmentDraft() }
        compose.waitUntil(10_000) { vm.uiState.value.assessmentDraftId != null }
        val id = vm.uiState.value.assessmentDraftId!!
        val context = compose.activity.applicationContext
        val row = runBlocking { AppDatabase.getInstance(context).assessmentDraftDao().getById(id)!! }
        assertEquals("Device Test Candidate", row.candidateFullName)
        assertEquals("9876543210", row.candidatePhone)
        assertFalse(row.candidatePublicNameConsent)
        assertNotNull(row.enrollmentSecret)
        compose.waitForIdle()
        compose.activityRule.scenario.recreate()
        compose.waitUntilExactlyOneExists(hasTestTag("unlock_pin"), 10_000)
        compose.onNodeWithTag("unlock_pin").performTextInput("0000")
        compose.onNodeWithTag("btn_unlock").performClick()
        compose.onNodeWithTag("unlock_pin").assertExists()
        compose.waitUntilExactlyOneExists(hasText("Unable to unlock", substring = true), 15_000)
        compose.onNodeWithTag("unlock_pin").performTextClearance()
        compose.onNodeWithTag("unlock_pin").performTextInput("1847")
        compose.onNodeWithTag("btn_unlock").performClick()
        compose.waitUntilDoesNotExist(hasTestTag("unlock_pin"), 15_000)
        assertEquals("Device Test Candidate", CandidateSecurity(context).profile()!!.fullName)
    }

    @Test fun forgottenPinErasesLocalDraftBeforeNewOnboarding() {
        check(compose.activity.packageName.endsWith(".p8validation"))
        compose.completeIntake(languageTag = "en", pin = "1847")
        val vm = ViewModelProvider(compose.activity)[AppViewModel::class.java]
        compose.runOnIdle { vm.startOrResumeAssessmentDraft() }
        compose.waitUntil(10_000) { vm.uiState.value.assessmentDraftId != null }
        val id = vm.uiState.value.assessmentDraftId!!
        val context = compose.activity.applicationContext
        compose.runOnIdle { vm.lockLocalData() }
        compose.onNodeWithText("Forgot security PIN?").performClick()
        compose.onNodeWithText("Erase local assessment and start again").performClick()
        compose.waitUntilExactlyOneExists(hasTestTag("lang_option_en"), 15_000)
        assertNull(CandidateSecurity(context).profile())
        assertNull(runBlocking { AppDatabase.getInstance(context).assessmentDraftDao().getById(id) })
    }
}
