// AGP 9+ provides Kotlin support built into com.android.library directly -- see
// media/build.gradle.kts and app/build.gradle.kts for the equivalent note.
plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.serialization)
}

android {
    namespace = "in.kaushalpramaan.core.seal"
    compileSdk = 36

    defaultConfig {
        minSdk = 26
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }

    testOptions {
        unitTests {
            isIncludeAndroidResources = true
        }
    }
}

tasks.withType<Test>().configureEach {
    jvmArgs(
        "--add-opens=java.base/java.lang=ALL-UNNAMED",
        "--add-opens=java.base/java.util=ALL-UNNAMED",
        "--add-opens=java.base/java.io=ALL-UNNAMED",
        "--add-opens=java.base/java.net=ALL-UNNAMED",
        "--add-opens=java.base/jdk.internal.access=ALL-UNNAMED",
        "--enable-native-access=ALL-UNNAMED",
    )
}

dependencies {
    // Canonical manifest JSON -- `api`, not `implementation`: SealManifest/SignedManifestPackage
    // are meant to be constructed/decoded directly by callers (:app), unlike the Tink
    // StreamingAead type, which is deliberately kept fully wrapped (see VaultCipher).
    api(libs.kotlinx.serialization.json)

    // Encrypted vault: Tink StreamingAead, keyset protected by Android Keystore via
    // AndroidKeysetManager -- never a hand-rolled cipher, never a hard-coded key.
    implementation(libs.tink.android)

    testImplementation(libs.junit)
    testImplementation(libs.androidx.test.ext.junit)
    testImplementation(libs.robolectric)

    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.kotlinx.coroutines.test)
}
