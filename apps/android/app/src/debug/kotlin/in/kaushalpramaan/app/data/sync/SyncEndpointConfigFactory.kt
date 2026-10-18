package `in`.kaushalpramaan.app.data.sync

import `in`.kaushalpramaan.app.BuildConfig
import android.content.Context

/** Debug-build-only real implementation: the base URL can be overridden at runtime (persisted
 * in a plain, non-sensitive SharedPreferences file -- this is a server hostname/IP, not a
 * secret) without a rebuild, since the physical test device's reachable LAN IP for the test
 * laptop running Docker Compose isn't known at build time. Falls back to
 * [BuildConfig.P6_TEST_ONLY_DEFAULT_SYNC_BASE_URL] (10.0.2.2, the standard emulator-to-host
 * alias) when no override has ever been set. Proven absent from release's compiled output by
 * app/build.gradle.kts's verifyP6SyncEndpointOverrideAbsentFromRelease task. */
internal class DebugOverridableSyncEndpointConfig(context: Context) : SyncEndpointConfig {
    private val prefs = context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    override fun baseUrl(): String =
        prefs.getString(KEY_OVERRIDE_URL, null)?.takeIf { it.isNotBlank() && supportsRuntimeOverride() }
            ?: BuildConfig.P6_TEST_ONLY_DEFAULT_SYNC_BASE_URL

    override fun supportsRuntimeOverride(): Boolean = BuildConfig.P6_TEST_ONLY_SYNC_ENDPOINT_OVERRIDE_ENABLED

    override fun setOverrideBaseUrl(url: String?) {
        prefs.edit().apply {
            if (url.isNullOrBlank()) remove(KEY_OVERRIDE_URL) else putString(KEY_OVERRIDE_URL, url.trim())
        }.apply()
    }

    companion object {
        private const val PREFS_NAME = "kp_p6_test_only_sync_endpoint"
        private const val KEY_OVERRIDE_URL = "override_base_url"
    }
}

fun provideSyncEndpointConfig(context: Context): SyncEndpointConfig = DebugOverridableSyncEndpointConfig(context)
