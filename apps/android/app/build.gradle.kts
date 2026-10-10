// AGP 9+ provides Kotlin support built into com.android.application directly --
// org.jetbrains.kotlin.android must not also be applied (see root build.gradle.kts).
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "in.kaushalpramaan.app"
    // compileSdk 36, not 35: several AndroidX libraries pulled in transitively
    // (activity 1.11.0, core-ktx 1.17.0) declare a minCompileSdk of 36 and AGP 9
    // enforces it as a hard build error, not a lint warning. This is independent
    // of minSdk (26, unchanged -- still the lowest OS version the app installs
    // on) and of which emulator API level is used to test on
    // (KaushalPramaan_API35 remains API 35; targetSdk/compileSdk being higher
    // than the test device's API level is normal and does not block
    // install/run there).
    compileSdk = 36

    defaultConfig {
        applicationId = "in.kaushalpramaan.app"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.3.0-p3"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        debug {
            isDebuggable = true
        }
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }

    buildFeatures {
        compose = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }

    testOptions {
        unitTests {
            isIncludeAndroidResources = true
        }
    }
}

// P-3 is offline-first by construction: no android.permission.INTERNET is declared anywhere
// in AndroidManifest.xml, and no networking dependency is declared here. This task fails the
// build if either ever creeps in, rather than relying on someone remembering to check.
val verifyNoNetworkDependencies = tasks.register("verifyNoNetworkDependencies") {
    doLast {
        // Strip XML comments first so this can't false-positive on explanatory
        // comments mentioning the permission names (as this file's manifest does).
        val manifest = file("src/main/AndroidManifest.xml").readText()
            .replace(Regex("<!--.*?-->", RegexOption.DOT_MATCHES_ALL), "")
        val usesPermissionTag = Regex("""<uses-permission\s+[^>]*android:name\s*=\s*"([^"]+)"""")
        val declared = usesPermissionTag.findAll(manifest).map { it.groupValues[1] }.toSet()
        check("android.permission.INTERNET" !in declared) {
            "P-3 must stay offline-first: AndroidManifest.xml must not declare android.permission.INTERNET"
        }
        check("android.permission.ACCESS_NETWORK_STATE" !in declared) {
            "P-3 must stay offline-first: AndroidManifest.xml must not declare ACCESS_NETWORK_STATE"
        }
    }
}
tasks.named("preBuild") {
    dependsOn(verifyNoNetworkDependencies)
}

dependencies {
    implementation(project(":core:mapping"))

    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.material.icons.extended)
    debugImplementation(libs.androidx.ui.tooling)
    debugImplementation(libs.androidx.ui.test.manifest)

    testImplementation(libs.junit)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.espresso.core)
    androidTestImplementation(libs.androidx.ui.test.junit4)
    androidTestImplementation(libs.androidx.test.uiautomator)
}
