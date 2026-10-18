package `in`.kaushalpramaan.app.ui.screens

import `in`.kaushalpramaan.app.R
import `in`.kaushalpramaan.app.data.AppViewModel
import `in`.kaushalpramaan.app.ui.components.KpBottomBar
import `in`.kaushalpramaan.app.ui.components.KpScaffold
import `in`.kaushalpramaan.app.ui.components.defaultMinTapTarget
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.KeyboardOptions
import `in`.kaushalpramaan.app.ui.components.KpButton as Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.Checkbox
import androidx.compose.foundation.layout.Row
import androidx.compose.runtime.rememberCoroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.Dispatchers
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp

@Composable
fun RegistrationScreen(viewModel: AppViewModel, onBack: () -> Unit, onContinue: () -> Unit) {
    val uiState by viewModel.uiState.collectAsState()
    var phone by remember { mutableStateOf(uiState.registration?.phone ?: "") }
    var fullName by remember { mutableStateOf(uiState.registration?.fullName ?: "") }
    var publicNameConsent by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    var pin by remember { mutableStateOf("") }
    var pinConfirm by remember { mutableStateOf("") }
    var errorRes by remember { mutableStateOf<Int?>(null) }

    KpScaffold(
        title = stringResource(R.string.registration_title),
        language = uiState.language,
        onLanguageChange = viewModel::setLanguage,
        onBack = onBack,
        bottomBar = { KpBottomBar {
            Button(
                onClick = {
                    errorRes = when {
                        fullName.trim().length < 2 || !fullName.any(Char::isLetter) -> R.string.registration_error_name
                        !phone.matches(Regex("[6-9][0-9]{9}")) -> R.string.registration_error_phone
                        pin.length != 4 -> R.string.registration_error_pin
                        pin != pinConfirm -> R.string.registration_error_pin_mismatch
                        else -> null
                    }
                    if (errorRes == null) {
                        busy = true
                        scope.launch(Dispatchers.Main.immediate) {
                            try {
                                viewModel.register(fullName, phone, pin.toCharArray(), publicNameConsent)
                                pin = ""; pinConfirm = ""
                                onContinue()
                            } finally { busy = false }
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth().defaultMinTapTarget().testTag("btn_register"),
                enabled = !busy,
            ) {
                Text(stringResource(R.string.registration_action_register))
            }
        } },
    ) { modifier ->
        Column(modifier = modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(18.dp)) {
            OutlinedTextField(value = fullName, onValueChange = { fullName = it.take(120) },
                label = { Text(stringResource(R.string.registration_name_label)) },
                singleLine = true, modifier = Modifier.fillMaxWidth().testTag("reg_name"))
            OutlinedTextField(
                value = phone,
                onValueChange = { if (it.length <= 10) phone = it.filter(Char::isDigit) },
                label = { Text(stringResource(R.string.registration_phone_label)) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                modifier = Modifier.fillMaxWidth().padding(top = 12.dp).defaultMinTapTarget().testTag("reg_phone"),
                singleLine = true,
            )
            OutlinedTextField(
                value = pin,
                onValueChange = { if (it.length <= 4) pin = it.filter(Char::isDigit) },
                label = { Text(stringResource(R.string.registration_pin_label)) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth().padding(top = 16.dp).defaultMinTapTarget().testTag("reg_pin"),
                singleLine = true,
            )
            OutlinedTextField(
                value = pinConfirm,
                onValueChange = { if (it.length <= 4) pinConfirm = it.filter(Char::isDigit) },
                label = { Text(stringResource(R.string.registration_pin_confirm_label)) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth().padding(top = 16.dp).defaultMinTapTarget().testTag("reg_pin_confirm"),
                singleLine = true,
            )

            errorRes?.let {
                Text(
                    stringResource(it),
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(top = 12.dp),
                )
            }
            Row(modifier = Modifier.padding(top = 18.dp)) {
                Checkbox(checked = publicNameConsent, onCheckedChange = { publicNameConsent = it }, modifier = Modifier.testTag("reg_public_name"))
                Text(stringResource(R.string.registration_public_name_consent))
            }
            `in`.kaushalpramaan.app.ui.components.KpCard(modifier = Modifier.fillMaxWidth().padding(top = 16.dp)) { Text(stringResource(R.string.registration_privacy), style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(14.dp)) }

            if (uiState.registration != null) {
                Text(
                    stringResource(R.string.registration_id_label) + ": " + uiState.registration!!.workerId,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(top = 16.dp),
                )
            }


        }
    }
}
