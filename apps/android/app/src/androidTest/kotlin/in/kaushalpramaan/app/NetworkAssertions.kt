package `in`.kaushalpramaan.app

import android.content.Context
import android.content.pm.PackageManager
import org.junit.Assert.assertEquals

/** Runtime half of the "no unnecessary network capability" guarantee, and the
 * runtime mirror of app/build.gradle.kts's `verifyExpectedNetworkPermissions`
 * / `verifyMergedManifestHasExpectedNetworkPermissions` allow-list checks.
 *
 * HISTORY -- this file used to assert the app held NO network permission at
 * all ("P-3 is offline-only"). That was correct for P-3, and became wrong at
 * P-6, which added real resumable HTTPS sync of the sealed outbox: the
 * manifest now deliberately declares INTERNET and ACCESS_NETWORK_STATE, and
 * the build-time check above *requires* them with the message "P6 genuinely
 * needs real networking". The two checks therefore contradicted each other,
 * and this one simply had not been run since P-6 (the P10 device gate ran a
 * curated subset). It also referenced `verifyNoNetworkDependencies`, a Gradle
 * task that no longer exists.
 *
 * What is still worth guaranteeing after P-6 is not "no networking" but
 * "nothing MORE than the two permissions sync actually needs" -- so a future
 * dependency (or a careless manifest edit) cannot quietly add location,
 * Wi-Fi-state or connectivity-mutating permissions to a worker's app.
 *
 * Offline *behaviour* is proven where it should be: by actually running the
 * declaration/matching journey with the radios off (see
 * OfflineAirplaneModeTest), not by removing the permission the sync feature
 * depends on. */
object NetworkAssertions {

    /** Exactly the network permissions P-6 sync needs. */
    private val EXPECTED_GRANTED = listOf(
        android.Manifest.permission.INTERNET,
        android.Manifest.permission.ACCESS_NETWORK_STATE,
    )

    /** Network-adjacent permissions this app must never acquire, including by
     * transitive manifest merge. Mirrors the build-time allow-list's intent. */
    private val MUST_NOT_HOLD = listOf(
        android.Manifest.permission.ACCESS_FINE_LOCATION,
        android.Manifest.permission.ACCESS_COARSE_LOCATION,
        android.Manifest.permission.ACCESS_WIFI_STATE,
        android.Manifest.permission.CHANGE_NETWORK_STATE,
        android.Manifest.permission.CHANGE_WIFI_STATE,
        android.Manifest.permission.READ_EXTERNAL_STORAGE,
    )

    fun assertAppHasOnlyExpectedNetworkPermissions(context: Context) {
        EXPECTED_GRANTED.forEach { assertPermissionGranted(context, it) }
        MUST_NOT_HOLD.forEach { assertPermissionDenied(context, it) }
    }

    private fun assertPermissionGranted(context: Context, permission: String) {
        assertEquals(
            "P6 sync needs $permission -- it must be declared (see " +
                "verifyExpectedNetworkPermissions in app/build.gradle.kts)",
            PackageManager.PERMISSION_GRANTED,
            context.packageManager.checkPermission(permission, context.packageName),
        )
    }

    private fun assertPermissionDenied(context: Context, permission: String) {
        assertEquals(
            "app must NOT hold $permission -- only INTERNET and " +
                "ACCESS_NETWORK_STATE are justified by P6 sync",
            PackageManager.PERMISSION_DENIED,
            context.packageManager.checkPermission(permission, context.packageName),
        )
    }
}
