package `in`.kaushalpramaan.app.data.sync

/**
 * Where to send sync traffic. Same three-piece split as P5's DebugExportHooks
 * (app/src/main interface + plain data, app/src/debug real implementation, app/src/release
 * no-op/fixed implementation, both behind one factory function signature) -- see
 * [provideSyncEndpointConfig]. Production code (SyncApiClient, SyncWorker) only ever depends
 * on this interface, never on which variant it's running in.
 */
interface SyncEndpointConfig {
    /** The base URL (scheme + host + optional port, no trailing slash) every sync request is
     * made against, e.g. "https://api.kaushalpramaan.example" or (debug only)
     * "http://10.0.2.2:8000". */
    fun baseUrl(): String

    /** Debug builds only: true if [setOverrideBaseUrl] can actually change [baseUrl]'s
     * result. Release's implementation always returns false and ignores any call to
     * [setOverrideBaseUrl] -- see FixedSyncEndpointConfig. Used purely to decide whether the
     * debug-only base-URL settings field renders at all. */
    fun supportsRuntimeOverride(): Boolean

    /** No-op in release. In debug, persists the override (SharedPreferences) so the physical
     * manual-gate tester can point sync at their laptop's real LAN IP without a rebuild. */
    fun setOverrideBaseUrl(url: String?)
}
