// AGP 9+ provides Kotlin support built into com.android.library directly --
// org.jetbrains.kotlin.android must not also be applied (see app/build.gradle.kts and
// root build.gradle.kts for the equivalent application-module note).
plugins {
    alias(libs.plugins.android.library)
}

android {
    namespace = "in.kaushalpramaan.media"
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

// Robolectric's native-SQLite/graphics shadow setup needs these JDK17+ module opens -- see
// app/build.gradle.kts for the detailed reasoning (identical here).
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
    implementation(project(":core:budget"))

    // Photo path: decode bounds/orientation without loading full pixel buffers
    // unnecessarily, write correctly-oriented JPEGs.
    implementation(libs.androidx.exifinterface)

    // Video path: real local Media3 Transformer transcoding (bitrate-before-resolution),
    // never a mock/no-op optimiser.
    implementation(libs.androidx.media3.transformer)
    implementation(libs.androidx.media3.common)
    implementation(libs.androidx.media3.effect)
    implementation(libs.kotlinx.coroutines.android)

    testImplementation(libs.junit)
    testImplementation(libs.androidx.test.ext.junit)
    testImplementation(libs.robolectric)
    testImplementation(libs.kotlinx.coroutines.test)

    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.kotlinx.coroutines.test)
}
