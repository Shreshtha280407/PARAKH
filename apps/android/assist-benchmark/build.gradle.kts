plugins { alias(libs.plugins.android.application) }
android {
    namespace = "in.kaushalpramaan.assist.benchmark"
    compileSdk = 36
    defaultConfig {
        applicationId = "in.kaushalpramaan.assist.benchmark"
        minSdk = 26; targetSdk = 36; versionCode = 1; versionName = "1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    buildTypes { release { isMinifyEnabled = false } }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_21; targetCompatibility = JavaVersion.VERSION_21 }
    androidResources { noCompress += "task" }
    sourceSets {
        getByName("androidTest") { assets.srcDirs(rootDir.resolve("../../ml/quality/fixtures")) }
        getByName("main") { assets.srcDirs(layout.buildDirectory.dir("generated/sourceAssets").get().asFile) }
    }
}
val generateAssistanceSourceStamp = tasks.register<Exec>("generateAssistanceSourceStamp") {
    val stamp = layout.buildDirectory.file("generated/sourceAssets/assistance-source.json")
    outputs.file(stamp)
    outputs.upToDateWhen { false }
    commandLine("python3", rootDir.resolve("../../tools/assistance_source.py").absolutePath, "--output", stamp.get().asFile.absolutePath)
}
tasks.named("preBuild") { dependsOn(generateAssistanceSourceStamp) }
tasks.register("verifyOfflineHarnessManifest") {
    dependsOn("processDebugManifest", "processReleaseManifest")
    doLast {
        for (variant in listOf("debug", "release")) {
            val taskName = if (variant == "debug") "processDebugManifest" else "processReleaseManifest"
            val text = layout.buildDirectory.file("intermediates/merged_manifests/$variant/$taskName/AndroidManifest.xml")
                .get().asFile.readText().replace(Regex("<!--.*?-->", RegexOption.DOT_MATCHES_ALL), "")
            check(!text.contains("android.permission.INTERNET")) { "$variant harness inherited INTERNET" }
            check(!text.contains("android.permission.ACCESS_NETWORK_STATE")) { "$variant harness inherited network-state permission" }
            check(!text.contains("EXTERNAL_STORAGE") && !text.contains("READ_MEDIA")) { "$variant harness inherited public media access" }
        }
    }
}
dependencies {
    implementation(project(":assist-quality"))
    implementation(project(":assist-hands"))
    implementation(libs.kotlinx.coroutines.android)
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.kotlinx.coroutines.test)
    androidTestImplementation(libs.androidx.exifinterface)
}
