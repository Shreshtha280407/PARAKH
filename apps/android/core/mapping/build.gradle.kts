import org.jetbrains.kotlin.gradle.tasks.KotlinCompile

plugins {
    alias(libs.plugins.kotlin.jvm)
    alias(libs.plugins.kotlin.serialization)
}

// core:mapping is deliberately a pure Kotlin/JVM module (no Android dependency) so its
// GoldenVectorsTest runs as a plain, fast JUnit `test` task:
//   ./gradlew :core:mapping:test --tests "*GoldenVectorsTest*"
// The :app module depends on this module and bundles it on-device like any other Kotlin code.

// Deliberately NOT pinning kotlin.jvmToolchain(): any explicit version here forces
// Gradle to resolve/auto-provision that exact JDK, which fails offline or on a CI
// runner that ships a different JDK than this dev machine's. Letting Kotlin use
// whichever JDK is already running Gradle works everywhere, this project has no
// actual need for a specific major version, and core:mapping is pure JVM code with
// no Android bytecode-level constraint to pin against.

dependencies {
    implementation(libs.kotlinx.serialization.json)
    testImplementation(libs.junit)
}

// Single source of truth: core:mapping NEVER hand-duplicates packs/ae-con-q0602's mapping
// data or ml/mapping's golden vectors. This task copies them in from the canonical repo
// locations before every build/test, so Kotlin reads exactly the same bytes Python does.
val repoRoot = rootDir.resolve("../..")

val syncPackResources = tasks.register<Copy>("syncPackResources") {
    from(repoRoot.resolve("packs/ae-con-q0602/mapping")) {
        into("mapping")
    }
    from(repoRoot.resolve("packs/ae-con-q0602/tasks.json"))
    into(layout.buildDirectory.dir("generated/packResources/pack"))
}

val syncGoldenVectors = tasks.register<Copy>("syncGoldenVectors") {
    from(repoRoot.resolve("ml/mapping/golden_vectors.jsonl"))
    into(layout.buildDirectory.dir("generated/packResources/pack"))
}

sourceSets {
    main {
        resources.srcDir(layout.buildDirectory.dir("generated/packResources"))
    }
}

// Both main (so :app sees them too) and test (so GoldenVectorsTest sees the
// contract file) need all three synced files -- registering resources.srcDir
// above only declares the source, these dependsOn wires the actual task order.
tasks.named("processResources") {
    dependsOn(syncPackResources, syncGoldenVectors)
}

tasks.named("processTestResources") {
    dependsOn(syncPackResources, syncGoldenVectors)
}

tasks.withType<KotlinCompile>().configureEach {
    compilerOptions {
        freeCompilerArgs.add("-Xjsr305=strict")
    }
}
