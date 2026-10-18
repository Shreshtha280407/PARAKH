package `in`.kaushalpramaan.app.ui.components

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.wifi.WifiInfo
import android.net.wifi.WifiManager
import android.os.Build
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CellTower
import androidx.compose.material.icons.filled.CloudDone
import androidx.compose.material.icons.filled.WifiOff
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalContentColor
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import `in`.kaushalpramaan.app.R
import kotlin.math.roundToInt

enum class ConnectionTransport { WIFI, MOBILE, OTHER }
data class ConnectionStatus(val internetAvailable: Boolean = false, val transport: ConnectionTransport = ConnectionTransport.OTHER, val wifiLevel: Int? = null)

/** Uses Android's default RSSI thresholds, without reading network names or
 * requesting location/Wi-Fi scan permissions. Null means no reliable RSSI. */
internal fun connectionStatus(capabilities: NetworkCapabilities?, wifi: WifiManager?): ConnectionStatus {
    if (capabilities == null) return ConnectionStatus()
    val validated = capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) && capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    val transport = when { capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> ConnectionTransport.WIFI; capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> ConnectionTransport.MOBILE; else -> ConnectionTransport.OTHER }
    val level = if (transport == ConnectionTransport.WIFI && Build.VERSION.SDK_INT >= 29) {
        val rssi = (capabilities.transportInfo as? WifiInfo)?.rssi?.takeIf { it in -126..-1 }
            ?: capabilities.signalStrength.takeIf { it in -126..-1 }
        rssi?.let { if (Build.VERSION.SDK_INT >= 30 && wifi != null) {
            val max = wifi.maxSignalLevel.coerceAtLeast(1)
            (wifi.calculateSignalLevel(it) * 4f / max).roundToInt().coerceIn(0, 4)
        } else {
            @Suppress("DEPRECATION")
            WifiManager.calculateSignalLevel(it, 5)
        } }
    } else null
    return ConnectionStatus(validated, transport, level)
}

@Composable
fun rememberConnectionStatus(): ConnectionStatus {
    val context = LocalContext.current.applicationContext
    val manager = remember(context) { context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager }
    val wifi = remember(context) { context.getSystemService(Context.WIFI_SERVICE) as? WifiManager }
    var state by remember(manager) { mutableStateOf(connectionStatus(manager.getNetworkCapabilities(manager.activeNetwork), wifi)) }
    DisposableEffect(manager, wifi) {
        var currentNetwork = manager.activeNetwork
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) { currentNetwork = network }
            override fun onCapabilitiesChanged(network: Network, capabilities: NetworkCapabilities) {
                if (network == currentNetwork) state = connectionStatus(capabilities, wifi)
            }
            override fun onLost(network: Network) {
                if (network == currentNetwork) { currentNetwork = null; state = ConnectionStatus() }
            }
        }
        manager.registerDefaultNetworkCallback(callback)
        onDispose { manager.unregisterNetworkCallback(callback) }
    }
    return state
}

@Composable
fun ConnectionIndicator(status: ConnectionStatus, modifier: Modifier = Modifier) {
    val label = when { !status.internetAvailable -> stringResource(R.string.offline_badge)
        status.transport == ConnectionTransport.WIFI && status.wifiLevel != null -> stringResource(R.string.wifi_signal_badge, status.wifiLevel)
        status.transport == ConnectionTransport.WIFI -> stringResource(R.string.wifi_online_badge)
        status.transport == ConnectionTransport.MOBILE -> stringResource(R.string.mobile_online_badge)
        else -> stringResource(R.string.online_badge) }
    val iconModifier = modifier.size(20.dp).testTag("connection_indicator").semantics { contentDescription = label }
    if (!status.internetAvailable) Icon(Icons.Filled.WifiOff, contentDescription = null, modifier = iconModifier)
    else if (status.transport == ConnectionTransport.WIFI) {
        val color = LocalContentColor.current
        Canvas(iconModifier) {
            val origin = Offset(size.width / 2, size.height * .88f)
            val level = status.wifiLevel
            drawCircle(color.copy(alpha = if (level != null && level >= 1) 1f else .25f), radius = size.width * .065f, center = origin)
            for (arc in 1..3) {
                val radius = size.height * (arc * .23f + .06f)
                drawArc(color.copy(alpha = if (level != null && level >= arc + 1) 1f else .25f), -135f, 90f, false,
                    topLeft = Offset(origin.x - radius, origin.y - radius), size = Size(radius * 2, radius * 2), style = Stroke(width = size.width * .09f, cap = StrokeCap.Round))
            }
        }
    } else Icon(if (status.transport == ConnectionTransport.MOBILE) Icons.Filled.CellTower else Icons.Filled.CloudDone, contentDescription = null, modifier = iconModifier)
}
