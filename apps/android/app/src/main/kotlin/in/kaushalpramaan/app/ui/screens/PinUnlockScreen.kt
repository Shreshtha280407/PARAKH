package `in`.kaushalpramaan.app.ui.screens

import android.app.Activity
import android.app.KeyguardManager
import android.content.Context
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppViewModel
import kotlinx.coroutines.launch
import kotlinx.coroutines.Dispatchers

@Composable
fun PinUnlockScreen(viewModel: AppViewModel, onErased: () -> Unit = {}) {
    val state by viewModel.uiState.collectAsState()
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var pin by remember { mutableStateOf("") }
    var confirm by remember { mutableStateOf("") }
    var error by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var eraseDialog by remember { mutableStateOf(false) }
    var credentialConfirmed by remember { mutableStateOf(false) }
    val credential = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        credentialConfirmed = it.resultCode == Activity.RESULT_OK
    }
    BackHandler { /* Locked data cannot be reached through navigation history. */ }
    Column(Modifier.fillMaxSize().padding(24.dp)) {
        Text(stringResource(R.string.pin_unlock_title), style = MaterialTheme.typography.headlineMedium)
        if (state.legacyPinRequired) {
            Text(stringResource(R.string.pin_legacy_explanation))
            Button(onClick = {
                val manager = context.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
                @Suppress("DEPRECATION")
                val intent = manager.createConfirmDeviceCredentialIntent("PARAKH", "Protect existing local assessment")
                if (intent != null) credential.launch(intent) else error = true
            }) { Text(stringResource(R.string.pin_device_verify)) }
        }
        OutlinedTextField(pin, { pin = it.filter { c -> c in '0'..'9' }.take(4) },
            label = { Text(stringResource(R.string.registration_pin_label)) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
            visualTransformation = PasswordVisualTransformation(), modifier = Modifier.testTag("unlock_pin"))
        if (state.legacyPinRequired) OutlinedTextField(confirm, { confirm = it.filter { c -> c in '0'..'9' }.take(4) },
            label = { Text(stringResource(R.string.registration_pin_confirm_label)) },
            visualTransformation = PasswordVisualTransformation())
        if (error) Text(stringResource(R.string.pin_unlock_error, (viewModel.pinLockRemainingMillis() / 1000) + 1),
            color = MaterialTheme.colorScheme.error)
        Button(enabled = !busy && pin.length == 4 && (!state.legacyPinRequired || credentialConfirmed && pin == confirm),
            modifier = Modifier.testTag("btn_unlock"), onClick = {
                busy = true
                scope.launch(Dispatchers.Main.immediate) {
                    try {
                        if (state.legacyPinRequired) viewModel.protectLegacyDraft(pin.toCharArray())
                        else error = !viewModel.unlockLocalData(pin.toCharArray())
                        pin = ""; confirm = ""
                    } finally { busy = false }
                }
            }) { Text(stringResource(R.string.pin_unlock_action)) }
        TextButton(onClick = { eraseDialog = true }) { Text(stringResource(R.string.pin_forgot_action)) }
    }
    if (eraseDialog) AlertDialog(onDismissRequest = { eraseDialog = false },
        title = { Text(stringResource(R.string.pin_forgot_action)) },
        text = { Text(stringResource(R.string.pin_erase_explanation)) },
        confirmButton = { Button(enabled = !busy, onClick = {
            busy = true
            scope.launch(Dispatchers.Main.immediate) {
                try {
                    viewModel.forgetPinAndEraseLocalData()
                    eraseDialog = false
                    onErased()
                }
                finally { busy = false }
            }
        }) { Text(stringResource(R.string.pin_erase_action)) } },
        dismissButton = { TextButton(onClick = { eraseDialog = false }) { Text(stringResource(android.R.string.cancel)) } })
}
