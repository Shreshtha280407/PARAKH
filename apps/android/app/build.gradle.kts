// AGP 9+ provides Kotlin support built into com.android.application directly --
// org.jetbrains.kotlin.android must not also be applied (see root build.gradle.kts).
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.ksp)
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
            // P4_TEST_ONLY: a debug-build-only override of the per-recording safety
            // ceiling, wired through the SAME production enforcement path as the real
            // T1-T5/total budgets (see EvidenceRepository). It exists purely so a
            // physical-device test can observe automatic stop-at-ceiling behaviour in
            // a few seconds instead of minutes. It is a compile-time constant baked
            // into the debug variant only -- the release block below hardcodes it to
            // false/0, so there is no runtime flag, setting, or code path that could
            // ever enable it in a release build.
            buildConfigField("boolean", "P4_TEST_ONLY_CEILING_ENABLED", "true")
            buildConfigField("long", "P4_TEST_ONLY_CEILING_BYTES", "4_194_304L")
        }
        release {
            isMinifyEnabled = false
            buildConfigField("boolean", "P4_TEST_ONLY_CEILING_ENABLED", "false")
            buildConfigField("long", "P4_TEST_ONLY_CEILING_BYTES", "0L")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }

    buildFeatures {
        compose = true
        buildConfig = true
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

// Robolectric 4.17's native-SQLite shadow (needed for the Room DAO tests under
// EvidenceRepositoryTest) reflects into a few JDK-internal classes that are not open by
// default on a modern JDK's strong module encapsulation -- without these, Robolectric fails
// during its own Application/SharedMemory setup with an IllegalAccessException, before any
// test code runs at all. This mirrors Robolectric's own documented JDK17+ troubleshooting
// guidance, extended with jdk.internal.access for the specific failure seen here.
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

// P4 evidence must be freshly captured through the app's own CameraX flow -- never
// imported via a Gallery/Photos picker or a generic document picker. This scans every
// Kotlin source file under src/main for the Intent actions those pickers use and fails the
// build if any appears, rather than relying on code review alone to keep it that way.
val verifyNoGalleryImportPath = tasks.register("verifyNoGalleryImportPath") {
    doLast {
        val forbidden = listOf("ACTION_PICK", "ACTION_GET_CONTENT", "ACTION_OPEN_DOCUMENT", "ACTION_OPEN_DOCUMENT_TREE")
        val offenders = fileTree("src/main") { include("**/*.kt") }.files.flatMap { f ->
            forbidden.filter { f.readText().contains(it) }.map { "${f.path}: $it" }
        }
        check(offenders.isEmpty()) {
            "P4 evidence must be captured in-app via CameraX, never imported via a Gallery/document picker. Found:\n" +
                offenders.joinToString("\n")
        }
    }
}
tasks.named("preBuild") {
    dependsOn(verifyNoGalleryImportPath)
}

// P4_TEST_ONLY: proves the debug-build-only safety-ceiling override is actually baked out
// of the release variant's BuildConfig as compile-time constants (false/0L) -- not merely
// "not used by any release UI path", which could silently regress. Fails the build if a
// future edit ever makes these non-false/non-zero for release.
val verifyP4TestCeilingDisabledInRelease = tasks.register("verifyP4TestCeilingDisabledInRelease") {
    dependsOn("generateReleaseBuildConfig")
    doLast {
        val buildConfig = file("build/generated/source/buildConfig/release/in/kaushalpramaan/app/BuildConfig.java").readText()
        val enabledMatch = Regex("""P4_TEST_ONLY_CEILING_ENABLED\s*=\s*(\w+);""").find(buildConfig)
        val bytesMatch = Regex("""P4_TEST_ONLY_CEILING_BYTES\s*=\s*(\w+);""").find(buildConfig)
        checkNotNull(enabledMatch) { "P4_TEST_ONLY_CEILING_ENABLED not found in release BuildConfig.java" }
        checkNotNull(bytesMatch) { "P4_TEST_ONLY_CEILING_BYTES not found in release BuildConfig.java" }
        check(enabledMatch.groupValues[1] == "false") {
            "P4_TEST_ONLY ceiling override must be false in release builds, found ${enabledMatch.groupValues[1]}"
        }
        check(bytesMatch.groupValues[1].removeSuffix("L") == "0") {
            "P4_TEST_ONLY ceiling override bytes must be 0 in release builds, found ${bytesMatch.groupValues[1]}"
        }
    }
}
tasks.named("check") {
    dependsOn(verifyP4TestCeilingDisabledInRelease)
}

// P4: Room's schema export (versioned migrations, not just "latest wins").
ksp {
    arg("room.schemaLocation", "$projectDir/schemas")
    arg("room.incremental", "true")
}

dependencies {
    implementation(project(":core:mapping"))

    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.kotlinx.coroutines.android)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.material.icons.extended)
    debugImplementation(libs.androidx.ui.tooling)
    debugImplementation(libs.androidx.ui.test.manifest)

    // P4: local encrypted draft storage.
    implementation(libs.androidx.room.runtime)
    implementation(libs.androidx.room.ktx)
    ksp(libs.androidx.room.compiler)
    implementation(libs.sqlcipher.android)
    implementation(libs.androidx.security.crypto)

    // P4: in-app CameraX capture (no Gallery/document-picker import).
    implementation(libs.androidx.camera.core)
    implementation(libs.androidx.camera.camera2)
    implementation(libs.androidx.camera.lifecycle)
    implementation(libs.androidx.camera.video)
    implementation(libs.androidx.camera.view)

    testImplementation(libs.junit)
    testImplementation(libs.androidx.test.ext.junit)
    testImplementation(libs.robolectric)
    testImplementation(libs.androidx.room.testing)
    testImplementation(libs.kotlinx.coroutines.test)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.espresso.core)
    androidTestImplementation(libs.androidx.ui.test.junit4)
    androidTestImplementation(libs.androidx.test.uiautomator)
    androidTestImplementation(libs.androidx.test.rules)
    androidTestImplementation(libs.androidx.room.testing)
    androidTestImplementation(libs.kotlinx.coroutines.test)
}
