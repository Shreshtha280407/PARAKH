package `in`.kaushalpramaan.app

import android.content.Context
import android.content.pm.PackageManager
import org.junit.Assert.assertEquals

/** Structural proof that this app cannot make an HTTP/network call at all,
 * regardless of the device's actual connectivity state: the OS denies the
 * INTERNET permission to any app that doesn't declare it in its manifest,
 * and AndroidManifest.xml here deliberately declares neither INTERNET nor
 * ACCESS_NETWORK_STATE (see app/build.gradle.kts's verifyNoNetworkDependencies
 * build-time check for the static half of this guarantee). */
object NetworkAssertions {
    fun assertAppHasNoInternetCapability(context: Context) {
        assertPermissionDenied(context, android.Manifest.permission.INTERNET)
        assertPermissionDenied(context, android.Manifest.permission.ACCESS_NETWORK_STATE)
    }

    private fun assertPermissionDenied(context: Context, permission: String) {
        val granted = context.packageManager.checkPermission(permission, context.packageName)
        assertEquals(
            "app must NOT hold $permission -- P-3 is offline-only",
            PackageManager.PERMISSION_DENIED,
            granted,
        )
    }
}
