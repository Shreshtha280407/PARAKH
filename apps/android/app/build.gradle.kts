// AGP 9+ provides Kotlin support built into com.android.application directly --
// org.jetbrains.kotlin.android must not also be applied (see root build.gradle.kts).
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
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
        versionName = "0.6.0-p6"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    // P6: lets Room's MigrationTestHelper (androidTest's AppDatabaseMigrationTest) find the
    // committed exported schema JSONs as real packaged assets, so a real migration can be
    // proven against a real prior-version database rather than only diffed schema-export JSON.
    sourceSets {
        getByName("androidTest") {
            assets.srcDirs("$projectDir/schemas")
        }
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
            // P5_TEST_ONLY: debug-build-only compile-time constants, same pattern as
            // P4_TEST_ONLY above. FORCE_OPTIMIZE lets a physical-device test force a smaller
            // virtual remaining budget through the SAME production BudgetLedger/optimiser
            // path (SealOrchestrator.ledgerFor), so real Media3 optimisation can be observed
            // on a short real clip instead of needing to fill the real 120 MB budget.
            // DEBUG_EXPORT_ENABLED gates the decrypt-for-verification export screen. Both are
            // hardcoded false in the release block below -- no runtime flag can enable either
            // in a release build.
            buildConfigField("boolean", "P5_TEST_ONLY_FORCE_OPTIMIZE_ENABLED", "true")
            buildConfigField("boolean", "P5_TEST_ONLY_DEBUG_EXPORT_ENABLED", "true")
            // P6_TEST_ONLY: debug builds may point sync at a local Docker-Compose
            // test backend over plain HTTP, and the base URL can be overridden
            // in-app at runtime (SyncEndpointConfig, app/src/debug) without a
            // rebuild -- needed because the physical device's reachable LAN IP
            // for the test laptop isn't known at build time. 10.0.2.2 is the
            // standard emulator-to-host alias, a reasonable zero-config default;
            // a real device on the same Wi-Fi/hotspot must be told the laptop's
            // actual LAN IP via the in-app debug-only field (see PreviewScreen).
            buildConfigField("boolean", "P6_TEST_ONLY_SYNC_ENDPOINT_OVERRIDE_ENABLED", "true")
            buildConfigField("String", "P6_TEST_ONLY_DEFAULT_SYNC_BASE_URL", "\"http://10.0.2.2:8000\"")
        }
        release {
            isMinifyEnabled = false
            buildConfigField("boolean", "P4_TEST_ONLY_CEILING_ENABLED", "false")
            buildConfigField("long", "P4_TEST_ONLY_CEILING_BYTES", "0L")
            buildConfigField("boolean", "P5_TEST_ONLY_FORCE_OPTIMIZE_ENABLED", "false")
            buildConfigField("boolean", "P5_TEST_ONLY_DEBUG_EXPORT_ENABLED", "false")
            buildConfigField("boolean", "P6_TEST_ONLY_SYNC_ENDPOINT_OVERRIDE_ENABLED", "false")
            // Never read by release's SyncEndpointConfig (app/src/release) --
            // release always uses its own hardcoded HTTPS production base URL,
            // with no override capability compiled in at all. This field only
            // exists so verifyP6TestOnlySyncOverrideDisabledInRelease below has
            // a concrete false/absent value to assert against.
            buildConfigField("String", "P6_TEST_ONLY_DEFAULT_SYNC_BASE_URL", "\"\"")
            // The real production API's HTTPS base URL. No deployed production
            // server exists for this MVP/hackathon build, so this is a
            // documented placeholder -- set it via
            // `-PreleaseSyncBaseUrl=https://the-real-host` at build time before
            // ever distributing a real release build (same pattern as the
            // server's own REPORT_SIGNING_PRIVATE_KEY/JWT_SECRET env vars: a
            // deliberate placeholder for local/demo use, not a hidden default
            // meant for production). Always HTTPS -- enforced architecturally,
            // not just by convention: FixedSyncEndpointConfig never reads a
            // scheme from anywhere else, and release's network security config
            // forbids cleartext outright regardless of this value.
            val releaseSyncBaseUrl = (project.findProperty("releaseSyncBaseUrl") as String?)
                ?: "https://api.kaushalpramaan.example"
            buildConfigField("String", "P6_RELEASE_SYNC_BASE_URL", "\"$releaseSyncBaseUrl\"")
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

// P6 pivot: P3/P4/P5 were offline-first by construction (no INTERNET/
// ACCESS_NETWORK_STATE anywhere). P6 genuinely needs real networking to sync
// the P5 sealed outbox -- so this task's JOB FLIPS from "neither permission
// may ever appear" to "exactly these two, and nothing else network/media/
// storage-related, may appear" -- the same source-only scan, asserting the
// opposite policy on purpose, not a leftover. Stays on preBuild (fast, no
// manifest-merge dependency).
val verifyExpectedNetworkPermissions = tasks.register("verifyExpectedNetworkPermissions") {
    doLast {
        // Strip XML comments first so this can't false-positive on explanatory
        // comments mentioning the permission names (as this file's manifest does).
        val manifest = file("src/main/AndroidManifest.xml").readText()
            .replace(Regex("<!--.*?-->", RegexOption.DOT_MATCHES_ALL), "")
        val usesPermissionTag = Regex("""<uses-permission\s+[^>]*?/>""")
        val declared = usesPermissionTag.findAll(manifest)
            .map { it.value }
            .filterNot { it.contains("""tools:node="remove"""") }
            .mapNotNull { Regex("""android:name\s*=\s*"([^"]+)"""").find(it)?.groupValues?.get(1) }
            .toSet()
        val expectedNetwork = setOf("android.permission.INTERNET", "android.permission.ACCESS_NETWORK_STATE")
        val allowed = expectedNetwork + setOf("android.permission.CAMERA", "android.permission.RECORD_AUDIO")
        val missing = expectedNetwork - declared
        check(missing.isEmpty()) {
            "P6 genuinely needs real networking: AndroidManifest.xml must declare $missing"
        }
        val unexpected = declared - allowed
        check(unexpected.isEmpty()) {
            "no unnecessary network/media/gallery/public-storage permission is allowed -- " +
                "found unexpected declared permission(s): $unexpected"
        }
    }
}

// P5 found a real gap in the source-only check above: it cannot see a permission a
// dependency's own manifest injects during Android's manifest merge step. This task
// inspects the real MERGED manifest for both variants -- the only artifact that reflects
// what dependencies actually contribute -- so a transitively-injected EXTRA permission
// (e.g. a future dependency wanting ACCESS_WIFI_STATE or coarse location "to help" with
// connectivity) cannot silently recur unnoticed. Wired to `check`, not `preBuild`, since it
// genuinely needs the manifest-merge tasks to have already run. Also asserts the
// networkSecurityConfig attribute is wired for both variants (see
// verifyReleaseForbidsCleartextTraffic below for the actual cleartext-policy proof).
val verifyMergedManifestHasExpectedNetworkPermissions = tasks.register("verifyMergedManifestHasExpectedNetworkPermissions") {
    dependsOn("processDebugMainManifest", "processReleaseMainManifest")
    doLast {
        val usesPermissionTag = Regex("""<uses-permission\s+[^>]*android:name\s*=\s*"([^"]+)"""")
        val expectedNetwork = setOf("android.permission.INTERNET", "android.permission.ACCESS_NETWORK_STATE")
        val allowed = expectedNetwork + setOf(
            "android.permission.CAMERA", "android.permission.RECORD_AUDIO",
            "in.kaushalpramaan.app.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION",
            // Transitively injected by androidx.work's own manifest, none of
            // them network/media/gallery/public-storage: WAKE_LOCK (keep the
            // CPU awake during a sync, same category P5 already allowed for
            // Media3 processing), RECEIVE_BOOT_COMPLETED (reschedule pending
            // sync work after a reboot -- required for correct resume
            // behaviour, not optional), FOREGROUND_SERVICE (WorkManager's
            // expedited-work execution path).
            "android.permission.WAKE_LOCK", "android.permission.RECEIVE_BOOT_COMPLETED",
            "android.permission.FOREGROUND_SERVICE",
        )
        for (variant in listOf("debug", "release")) {
            val mergedManifestFile = fileTree(layout.buildDirectory.dir("intermediates/merged_manifest/$variant")) {
                include("**/AndroidManifest.xml")
            }.files.firstOrNull()
            checkNotNull(mergedManifestFile) { "could not locate the merged $variant manifest" }
            val merged = mergedManifestFile.readText().replace(Regex("<!--.*?-->", RegexOption.DOT_MATCHES_ALL), "")
            val declaredInMerged = usesPermissionTag.findAll(merged).map { it.groupValues[1] }.toSet()
            val missing = expectedNetwork - declaredInMerged
            check(missing.isEmpty()) {
                "the real MERGED $variant manifest is missing expected permission(s) $missing"
            }
            val unexpected = declaredInMerged - allowed
            check(unexpected.isEmpty()) {
                "the real MERGED $variant manifest declares unexpected permission(s) $unexpected -- " +
                    "a dependency may be injecting a network/storage permission this app doesn't need; " +
                    "add a tools:node=\"remove\" override if so"
            }
            check(merged.contains("""android:networkSecurityConfig="@xml/network_security_config"""")) {
                "the real MERGED $variant manifest must reference android:networkSecurityConfig=" +
                    "\"@xml/network_security_config\" (see verifyReleaseForbidsCleartextTraffic)"
            }
        }
    }
}
tasks.named("check") {
    dependsOn(verifyMergedManifestHasExpectedNetworkPermissions)
}
tasks.named("preBuild") {
    dependsOn(verifyExpectedNetworkPermissions)
}

// P6 rule 3: "Upload over HTTPS in release builds only. Cleartext HTTP may be allowed
// solely in the DEBUG variant ... Add a release-build regression test proving a release
// build does not allow cleartext traffic." Two independent, real proofs rather than one:
// (1) release's EFFECTIVE network security config (main's, since release has no overlay)
// forbids cleartext outright; (2) debug's override file exists and actually differs (proving
// the permissive config is a genuine, intentional debug-only overlay, not an accidental
// global default that release would also pick up).
val verifyReleaseForbidsCleartextTraffic = tasks.register("verifyReleaseForbidsCleartextTraffic") {
    doLast {
        val mainConfig = file("src/main/res/xml/network_security_config.xml")
        checkNotNull(mainConfig.takeIf { it.exists() }) { "missing src/main/res/xml/network_security_config.xml" }
        val mainText = mainConfig.readText()
        check(Regex("""cleartextTrafficPermitted\s*=\s*"false"""").containsMatchIn(mainText)) {
            "src/main/res/xml/network_security_config.xml (release's EFFECTIVE config -- release has " +
                "no debug-only overlay) must set cleartextTrafficPermitted=\"false\""
        }

        val debugConfig = file("src/debug/res/xml/network_security_config.xml")
        checkNotNull(debugConfig.takeIf { it.exists() }) {
            "missing src/debug/res/xml/network_security_config.xml -- the debug-only cleartext " +
                "override must exist as its own separate resource overlay, never edited into main's"
        }
        val debugText = debugConfig.readText()
        check(Regex("""cleartextTrafficPermitted\s*=\s*"true"""").containsMatchIn(debugText)) {
            "src/debug/res/xml/network_security_config.xml must set cleartextTrafficPermitted=\"true\" " +
                "(that's the whole point of the debug-only override); found no such attribute"
        }

        val mainManifest = file("src/main/AndroidManifest.xml").readText()
        check(mainManifest.contains("""android:usesCleartextTraffic="false"""")) {
            "src/main/AndroidManifest.xml must keep android:usesCleartextTraffic=\"false\" as a " +
                "defense-in-depth legacy fallback alongside the network security config"
        }
    }
}
tasks.named("check") {
    dependsOn(verifyReleaseForbidsCleartextTraffic)
}

// P6_TEST_ONLY: same false/absent-in-release proof pattern as
// verifyP4TestCeilingDisabledInRelease/verifyP5DebugFeaturesDisabledInRelease above, for the
// debug-only sync-endpoint-override capability.
val verifyP6TestOnlySyncOverrideDisabledInRelease = tasks.register("verifyP6TestOnlySyncOverrideDisabledInRelease") {
    dependsOn("generateReleaseBuildConfig")
    doLast {
        val buildConfig = file("build/generated/source/buildConfig/release/in/kaushalpramaan/app/BuildConfig.java").readText()
        val enabledMatch = Regex("""P6_TEST_ONLY_SYNC_ENDPOINT_OVERRIDE_ENABLED\s*=\s*(\w+);""").find(buildConfig)
        checkNotNull(enabledMatch) { "P6_TEST_ONLY_SYNC_ENDPOINT_OVERRIDE_ENABLED not found in release BuildConfig.java" }
        check(enabledMatch.groupValues[1] == "false") {
            "P6_TEST_ONLY sync endpoint override must be false in release builds, found ${enabledMatch.groupValues[1]}"
        }
    }
}
tasks.named("check") {
    dependsOn(verifyP6TestOnlySyncOverrideDisabledInRelease)
}

// P6_TEST_ONLY sync-endpoint override (same three-piece pattern as P5's debug export --
// main interface, app/src/debug real implementation, app/src/release no-op): proves the REAL
// overridable-base-URL implementation is genuinely absent from release's compiled output, not
// merely disabled by the BuildConfig flag above (which only proves release's DEFAULT is
// false/empty -- this proves the capability to override it at all doesn't exist in release).
val verifyP6SyncEndpointOverrideAbsentFromRelease = tasks.register("verifyP6SyncEndpointOverrideAbsentFromRelease") {
    dependsOn("compileDebugKotlin", "compileReleaseKotlin")
    doLast {
        fun findClass(variantDir: String, simpleClassName: String): File? =
            fileTree(layout.buildDirectory.dir("intermediates")) {
                include("**/$variantDir/**/in/kaushalpramaan/app/data/sync/$simpleClassName.class")
            }.files.firstOrNull()

        checkNotNull(findClass("debug", "DebugOverridableSyncEndpointConfig")) {
            "DebugOverridableSyncEndpointConfig.class must be present in the debug build's compiled output"
        }
        check(findClass("release", "DebugOverridableSyncEndpointConfig") == null) {
            "DebugOverridableSyncEndpointConfig.class (the real runtime-overridable sync base URL) " +
                "must never exist in the release build's compiled output"
        }
        checkNotNull(findClass("release", "FixedSyncEndpointConfig")) {
            "FixedSyncEndpointConfig.class must be present in the release build's compiled output " +
                "(the sync-endpoint-override feature must be correctly variant-split, not silently missing from both)"
        }
    }
}
tasks.named("check") {
    dependsOn(verifyP6SyncEndpointOverrideAbsentFromRelease)
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

// P5_TEST_ONLY: same proof as verifyP4TestCeilingDisabledInRelease above, for the two P5
// debug-only compile-time flags (forced-budget optimiser test mode, decrypt-for-verification
// debug export).
val verifyP5DebugFeaturesDisabledInRelease = tasks.register("verifyP5DebugFeaturesDisabledInRelease") {
    dependsOn("generateReleaseBuildConfig")
    doLast {
        val buildConfig = file("build/generated/source/buildConfig/release/in/kaushalpramaan/app/BuildConfig.java").readText()
        for (field in listOf("P5_TEST_ONLY_FORCE_OPTIMIZE_ENABLED", "P5_TEST_ONLY_DEBUG_EXPORT_ENABLED")) {
            val match = Regex("""$field\s*=\s*(\w+);""").find(buildConfig)
            checkNotNull(match) { "$field not found in release BuildConfig.java" }
            check(match.groupValues[1] == "false") { "$field must be false in release builds, found ${match.groupValues[1]}" }
        }
    }
}
tasks.named("check") {
    dependsOn(verifyP5DebugFeaturesDisabledInRelease)
}

// P5_TEST_ONLY debug export (spec part H.3/H.7): proves the REAL decrypting implementation
// (app/src/debug's RealDebugExportHooks) is genuinely absent from the release variant's
// compiled output -- not merely disabled by a runtime/BuildConfig flag, which
// verifyP5DebugFeaturesDisabledInRelease above already covers for the OTHER P5 debug flag.
// Also asserts the real class IS present in the debug variant and that release's no-op
// counterpart (NoOpDebugExportHooks) is the one actually compiled in, so this fails loudly if
// the whole feature silently vanished from both variants instead of being correctly
// variant-split.
val verifyP5DebugExportAbsentFromRelease = tasks.register("verifyP5DebugExportAbsentFromRelease") {
    dependsOn("compileDebugKotlin", "compileReleaseKotlin")
    doLast {
        fun findClass(variantDir: String, simpleClassName: String): File? =
            fileTree(layout.buildDirectory.dir("intermediates")) {
                include("**/$variantDir/**/in/kaushalpramaan/app/debug/$simpleClassName.class")
            }.files.firstOrNull()

        checkNotNull(findClass("debug", "RealDebugExportHooks")) {
            "RealDebugExportHooks.class must be present in the debug build's compiled output"
        }
        check(findClass("release", "RealDebugExportHooks") == null) {
            "RealDebugExportHooks.class (the real decrypting P5_TEST_ONLY debug-export implementation) " +
                "must never exist in the release build's compiled output"
        }
        checkNotNull(findClass("release", "NoOpDebugExportHooks")) {
            "NoOpDebugExportHooks.class must be present in the release build's compiled output " +
                "(the debug export feature must be correctly variant-split, not silently missing from both)"
        }
    }
}
tasks.named("check") {
    dependsOn(verifyP5DebugExportAbsentFromRelease)
}

// P4: Room's schema export (versioned migrations, not just "latest wins").
ksp {
    arg("room.schemaLocation", "$projectDir/schemas")
    arg("room.incremental", "true")
}

dependencies {
    implementation(project(":core:mapping"))
    implementation(project(":core:budget"))
    implementation(project(":core:seal"))
    implementation(project(":media"))

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

    // P6: resumable WorkManager sync of the P5 sealed outbox over HTTPS.
    implementation(libs.androidx.work.runtime.ktx)
    implementation(libs.okhttp)

    testImplementation(libs.junit)
    testImplementation(libs.androidx.test.ext.junit)
    testImplementation(libs.robolectric)
    testImplementation(libs.androidx.room.testing)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.androidx.work.testing)
    testImplementation(libs.okhttp.mockwebserver)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.espresso.core)
    androidTestImplementation(libs.androidx.ui.test.junit4)
    androidTestImplementation(libs.androidx.test.uiautomator)
    androidTestImplementation(libs.androidx.test.rules)
    androidTestImplementation(libs.androidx.room.testing)
    androidTestImplementation(libs.kotlinx.coroutines.test)
    androidTestImplementation(libs.androidx.work.testing)
    androidTestImplementation(libs.okhttp.mockwebserver)
}
