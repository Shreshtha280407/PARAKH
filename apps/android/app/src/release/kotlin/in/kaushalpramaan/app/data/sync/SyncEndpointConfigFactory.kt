package `in`.kaushalpramaan.app.data.sync

import `in`.kaushalpramaan.app.BuildConfig
import android.content.Context

/** Release-build implementation: always the real, hardcoded production HTTPS base URL, with
 * no override capability compiled in at all -- [setOverrideBaseUrl] is a genuine no-op, not
 * merely "disabled by a flag." Proven by app/build.gradle.kts's
 * verifyP6SyncEndpointOverrideAbsentFromRelease task, which asserts this class (not
 * DebugOverridableSyncEndpointConfig) is the one actually compiled into a release build. */
internal class FixedSyncEndpointConfig : SyncEndpointConfig {
    override fun baseUrl(): String = BuildConfig.P6_RELEASE_SYNC_BASE_URL
    override fun supportsRuntimeOverride(): Boolean = false
    override fun setOverrideBaseUrl(url: String?) { /* no-op: release has no override capability */ }
}

fun provideSyncEndpointConfig(context: Context): SyncEndpointConfig = FixedSyncEndpointConfig()
