plugins { alias(libs.plugins.android.library) }
android {
    namespace = "in.kaushalpramaan.assist.hands"
    compileSdk = 36
    defaultConfig { minSdk = 26; testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner" }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_21; targetCompatibility = JavaVersion.VERSION_21 }
    androidResources { noCompress += "task" }
}
dependencies {
    api(project(":assist-quality"))
    implementation("com.google.mediapipe:tasks-vision:0.10.35")
    implementation(libs.kotlinx.coroutines.android)
    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.kotlinx.coroutines.test)
}
