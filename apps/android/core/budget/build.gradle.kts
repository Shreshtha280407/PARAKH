plugins {
    alias(libs.plugins.kotlin.jvm)
}

// core:budget is deliberately a pure Kotlin/JVM module -- no Android dependency, no Room, no
// filesystem access. It is the one place P5's final-evidence budget rules are expressed: given
// a source-of-truth list of final (READY) evidence items, it always *recomputes* task/total
// usage and accept/fit decisions from that list, never from cached or incrementally-maintained
// counters. :media and :app both depend on this module rather than each re-implementing budget
// arithmetic.
//
// Deliberately NOT pinning kotlin.jvmToolchain() -- same reasoning as core:mapping's build file.

dependencies {
    testImplementation(libs.junit)
}
