package `in`.kaushalpramaan.app

import `in`.kaushalpramaan.app.data.DeclarationCardCatalog
import `in`.kaushalpramaan.app.data.draft.AppDatabase
import `in`.kaushalpramaan.core.mapping.RulesLoader
import android.content.pm.PackageManager
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.SemanticsNodeInteraction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.ComposeTestRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.waitUntilExactlyOneExists
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import org.junit.Assume
import org.junit.rules.TestRule
import org.junit.runner.Description
import org.junit.runners.model.Statement

/** Scrolls into view when the node sits inside a scrollable container;
 * tolerates screens with no scroll container at all (performScrollTo()
 * throws AssertionError there rather than being a no-op). */
fun SemanticsNodeInteraction.scrollToIfPossible(): SemanticsNodeInteraction {
    try {
        performScrollTo()
    } catch (_: AssertionError) {
        // no scrollable ancestor -- the node is already on-screen
    }
    return this
}

/** Shared navigation helpers for the instrumented P-3 journey tests. Every
 * screen is driven through real taps on the testTags set on production
 * composables (see each screen file) -- not through ViewModel shortcuts --
 * so these tests exercise the actual wired-up UI, not just the business
 * logic (which GoldenVectorsTest/MatcherTest in core:mapping already cover
 * exhaustively). */

val ALL_DECLARATION_ITEM_IDS: List<String> by lazy {
    val rules = RulesLoader.load()
    (DeclarationCardCatalog.allCards(rules) + DeclarationCardCatalog.allTools(rules)).map { it.id }
}

/** P4 drafts are durable (Room/SQLCipher + private files) and survive across Activity
 * launches within the same instrumented test process -- unlike P3's in-memory-only state,
 * a fresh MainActivity launch alone no longer guarantees a fresh app state (a draft left
 * behind by a previous test in the same instrumentation run would make this test's app
 * auto-resume straight to the task list instead of showing the language screen first).
 * Journey tests that assume a clean start must run this BEFORE the Activity launches --
 * declare it with a lower @Rule(order=...) than the ComposeTestRule, since rule `apply()`
 * wrapping (including the Activity launch) happens outside @Before methods, so a @Before
 * cleanup alone would run too late. */
class ClearP4DraftBeforeTest : TestRule {
    override fun apply(base: Statement, description: Description): Statement = object : Statement() {
        override fun evaluate() {
            // Close and drop the cached AppDatabase singleton FIRST: instrumented tests
            // share one app process across every @Test method/class in the same run, so an
            // already-open connection from a previous test would otherwise keep serving
            // old data regardless of the file deletion below.
            AppDatabase.resetInstanceForTesting()
            val context = InstrumentationRegistry.getInstrumentation().targetContext
            `in`.kaushalpramaan.app.data.CandidateSecurity(context).clear()
            val dbFile = context.getDatabasePath("kp_drafts.db")
            dbFile.delete()
            File(dbFile.path + "-wal").delete()
            File(dbFile.path + "-shm").delete()
            File(context.filesDir, "drafts").deleteRecursively()
            base.evaluate()
        }
    }
}

/** [GrantPermissionRule] (androidx.test's UiAutomation-based grant) and a raw `pm grant`
 * shell command both ultimately call the same privileged PackageManager API. On this
 * specific OEM build (confirmed via a direct `adb shell pm grant` attempt returning
 * `SecurityException: Neither user 2000 nor current process has
 * android.permission.GRANT_RUNTIME_PERMISSIONS`), even the `shell` UID has had that
 * capability removed -- a device/OS policy restriction, not an app or test defect. Camera
 * capture itself is NOT broken by this; only *unattended, automated* permission granting
 * is unavailable here. Real capture is proven by the MANUAL_P4_GATE (a human taps "Allow"),
 * and the repository-level lifecycle/budget logic is proven exhaustively by
 * EvidenceRepositoryTest without needing the permission at all. Rather than let tests that
 * depend on a pre-granted permission fail opaquely, this rule detects the restriction and
 * skips (JUnit "assumption failed", a distinct, honest status -- not a false pass and not
 * an unexplained failure) with a clear reason. */
class GrantPermissionsViaShell(private vararg val permissions: String) : TestRule {
    override fun apply(base: Statement, description: Description): Statement = object : Statement() {
        override fun evaluate() {
            val context = InstrumentationRegistry.getInstrumentation().targetContext
            val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
            for (permission in permissions) {
                val pfd = automation.executeShellCommand("pm grant ${context.packageName} $permission")
                // Reading to EOF blocks until the shell command actually finishes, so the
                // permission is genuinely granted (or the failure is genuinely known) before
                // the Activity under test launches.
                val output = android.os.ParcelFileDescriptor.AutoCloseInputStream(pfd).use { it.readBytes() }.decodeToString()
                // Don't trust the shell command's own exit text alone -- this OEM build has
                // been observed to report no error yet still not actually apply the grant
                // (a silent policy override, not a thrown exception). Verify directly against
                // the real permission state instead.
                val actuallyGranted = context.checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED
                Assume.assumeTrue(
                    "Skipping: this device's OS build does not allow unattended runtime permission " +
                        "granting ($permission) -- real capture is proven by the manual device gate instead. " +
                        "Shell output: ${output.lineSequence().firstOrNull().orEmpty()}",
                    actuallyGranted,
                )
            }
            base.evaluate()
        }
    }
}

fun ComposeTestRule.tapTag(tag: String) {
    onNodeWithTag(tag).scrollToIfPossible().performClick()
}

/** language -> consent -> registration, ending on the declaration screen. */
@OptIn(ExperimentalTestApi::class)
fun ComposeTestRule.completeIntake(languageTag: String, phone: String = "9876543210", pin: String = "1234") {
    // The app always shows a brief LOADING screen first (the one-time launch check: reconcile
    // any interrupted P4 draft, then resolve whether to resume or start fresh -- see
    // AppNavGraph's LOADING route) before navigating to LANGUAGE. Waiting for the language
    // option to actually exist, rather than tapping immediately, avoids racing that
    // Loading->Language navigation on its very first frame.
    val languageTag2 = if (languageTag == "hi") "lang_option_hi" else "lang_option_en"
    waitUntilExactlyOneExists(hasTestTag(languageTag2), timeoutMillis = 10_000)
    tapTag(languageTag2)
    tapTag("btn_continue")

    tapTag("consent_checkbox")
    tapTag("btn_continue")

    onNodeWithTag("reg_name").scrollToIfPossible().performTextInput("Device Test Candidate")
    onNodeWithTag("reg_phone").scrollToIfPossible().performTextInput(phone)
    onNodeWithTag("reg_pin").scrollToIfPossible().performTextInput(pin)
    onNodeWithTag("reg_pin_confirm").scrollToIfPossible().performTextInput(pin)
    tapTag("btn_register")
    // PIN derivation runs off the UI thread. Continue only once durable
    // registration completes and navigation reaches the declaration.
    waitUntilExactlyOneExists(hasTestTag("declaration_lazy_column"), timeoutMillis = 15_000)
}

/** DeclarationScreen's list is a LazyColumn (26 items + the non-scored
 * work-setting/prior-training/free-text block): a far-off item's
 * semantics node does not exist at all until it scrolls into the composed
 * window, so onNodeWithTag(tag).performScrollTo() can't find it to scroll to
 * it (chicken-and-egg). performScrollToNode() instead scrolls the CONTAINER
 * (declaration_lazy_column) using the lazy list's own index-aware scroll
 * action while searching for the matcher, which works for not-yet-composed
 * items. */
fun ComposeTestRule.tapInLazyColumn(containerTag: String, targetTag: String) {
    onNodeWithTag(containerTag).performScrollToNode(hasTestTag(targetTag))
    onNodeWithTag(targetTag).performClick()
}

/** Sets the same often/sometimes/never answer on every one of the 26
 * declaration items (20 cards + 6 tools), then taps through to the match
 * result screen. Used for
 * the three clean reference scenarios (all-often -> appropriate_match,
 * all-sometimes -> partial_match, all-never -> not_appropriate_match) that
 * ml/mapping/golden_vectors.jsonl G001/G002/G003 already pin exactly, so
 * the expected on-screen result here is known, not guessed. */
fun ComposeTestRule.answerAllDeclarationItems(answer: String) {
    for (id in ALL_DECLARATION_ITEM_IDS) {
        tapInLazyColumn("declaration_lazy_column", "answer_${id}_$answer")
    }
    tapInLazyColumn("declaration_lazy_column", "btn_see_match")
}
