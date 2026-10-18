package `in`.kaushalpramaan.app.ui

import android.net.NetworkCapabilities
import `in`.kaushalpramaan.app.ui.components.ConnectionTransport
import `in`.kaushalpramaan.app.ui.components.connectionStatus
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.shadow.api.Shadow
import org.robolectric.shadows.ShadowNetworkCapabilities

@RunWith(RobolectricTestRunner::class)
class ConnectivityStatusTest {
    private fun capabilities(transport: Int, validated: Boolean): NetworkCapabilities = ShadowNetworkCapabilities.newInstance().also {
        val shadow = Shadow.extract<ShadowNetworkCapabilities>(it)
        shadow.addTransportType(transport)
        shadow.addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
        if (validated) shadow.addCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }
    @Test fun noDefaultNetworkIsOffline() {
        assertFalse(connectionStatus(null, null).internetAvailable)
    }
    @Test fun wifiWithoutValidatedInternetIsOffline() {
        val state = connectionStatus(capabilities(NetworkCapabilities.TRANSPORT_WIFI, false), null)
        assertFalse(state.internetAvailable)
        assertEquals(ConnectionTransport.WIFI, state.transport)
    }
    @Test fun validatedWifiIsOnlineWithoutFabricatingMissingSignalData() {
        val state = connectionStatus(capabilities(NetworkCapabilities.TRANSPORT_WIFI, true), null)
        assertTrue(state.internetAvailable)
        assertEquals(ConnectionTransport.WIFI, state.transport)
        assertNull(state.wifiLevel)
    }
    @Test fun mobileInternetIsDistinguishedFromWifi() {
        val state = connectionStatus(capabilities(NetworkCapabilities.TRANSPORT_CELLULAR, true), null)
        assertTrue(state.internetAvailable)
        assertEquals(ConnectionTransport.MOBILE, state.transport)
        assertNull(state.wifiLevel)
    }
}
