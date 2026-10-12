// AGP 9+ has built-in Kotlin support for Android modules -- the separate
// org.jetbrains.kotlin.android plugin must NOT be applied alongside it
// (see app/build.gradle.kts). core:mapping is a plain Kotlin/JVM module and
// still needs org.jetbrains.kotlin.jvm explicitly.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.android.library) apply false
    alias(libs.plugins.kotlin.jvm) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
}
