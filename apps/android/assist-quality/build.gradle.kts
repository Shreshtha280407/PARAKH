plugins { alias(libs.plugins.android.library) }
android {
    namespace = "in.kaushalpramaan.assist.quality"
    compileSdk = 36
    defaultConfig { minSdk = 26; testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner" }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_21; targetCompatibility = JavaVersion.VERSION_21 }
    testOptions { unitTests.isIncludeAndroidResources = true }
}
dependencies {
    implementation(libs.androidx.exifinterface)
    implementation(libs.kotlinx.coroutines.android)
    testImplementation(libs.junit)
    testImplementation(libs.robolectric)
    testImplementation(libs.androidx.test.ext.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.kotlinx.coroutines.test)
}
tasks.withType<Test>().configureEach {
    val golden = rootDir.resolve("../../ml/quality/fixtures/golden_metrics.tsv")
    inputs.file(golden)
    systemProperty("quality.golden.file", golden.absolutePath)
    jvmArgs("--add-opens=java.base/java.lang=ALL-UNNAMED", "--add-opens=java.base/java.util=ALL-UNNAMED",
        "--add-opens=java.base/java.io=ALL-UNNAMED", "--add-opens=java.base/java.net=ALL-UNNAMED",
        "--add-opens=java.base/jdk.internal.access=ALL-UNNAMED", "--enable-native-access=ALL-UNNAMED")
}
