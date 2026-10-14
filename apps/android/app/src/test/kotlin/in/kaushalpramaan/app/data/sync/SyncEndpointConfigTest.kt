package `in`.kaushalpramaan.app.data.sync

import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** This module's own build config is "debug" (Robolectric always runs against the debug
 * variant's compiled sources) -- so [provideSyncEndpointConfig] here resolves to
 * [DebugOverridableSyncEndpointConfig]; [FixedSyncEndpointConfig]'s own release-only behaviour
 * (always the hardcoded production URL, override is a genuine no-op) is proven never to even
 * exist in a release build's compiled output by
 * app/build.gradle.kts's verifyP6SyncEndpointOverrideAbsentFromRelease task -- see
 * docs/gates/P6.md for why that static proof is the right tool for an "absent", not
 * "behaves correctly", claim. */
@RunWith(RobolectricTestRunner::class)
class SyncEndpointConfigTest {

    @Test
    fun debug_config_defaults_to_the_build_configs_emulator_alias_when_never_overridden() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val config = provideSyncEndpointConfig(context)
        assertTrue(config.supportsRuntimeOverride())
        assertEquals(`in`.kaushalpramaan.app.BuildConfig.P6_TEST_ONLY_DEFAULT_SYNC_BASE_URL, config.baseUrl())
    }

    @Test
    fun debug_config_override_persists_and_is_read_back_by_a_fresh_instance() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        provideSyncEndpointConfig(context).setOverrideBaseUrl("http://192.168.1.50:8000")
        val secondInstance = provideSyncEndpointConfig(context)
        assertEquals("http://192.168.1.50:8000", secondInstance.baseUrl())
    }

    @Test
    fun debug_config_clearing_the_override_falls_back_to_the_default_again() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val config = provideSyncEndpointConfig(context)
        config.setOverrideBaseUrl("http://192.168.1.50:8000")
        config.setOverrideBaseUrl(null)
        assertEquals(`in`.kaushalpramaan.app.BuildConfig.P6_TEST_ONLY_DEFAULT_SYNC_BASE_URL, config.baseUrl())
    }

    // FixedSyncEndpointConfig (app/src/release) is not on this debug-variant test's
    // compilation classpath at all -- that's exactly the property
    // verifyP6SyncEndpointOverrideAbsentFromRelease proves (see app/build.gradle.kts), and the
    // class itself is a trivial two-line hardcoded-return/no-op, not independently worth a
    // dedicated per-build-type test source set just to re-assert it.
}
