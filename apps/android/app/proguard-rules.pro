# SQLCipher registers Java methods/fields by name in JNI_OnLoad, including
# SQLiteDatabase.lastInsertRow(), which can have no direct Java call site.
# Preserve this native ABI. Verified by the P8 shrunk-APK process-recovery run;
# omitting it reproduces a JNI abort on the physical API36 device.
-keep class net.sqlcipher.** { *; }

# The pinned MediaPipe AARs omit upstream's native callback keep rules:
# https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/java/com/google/mediapipe/framework/proguard.pgcfg
# Scope these to the documented JNI entry points; retaining the whole SDK also
# retains unused profiling/template APIs whose optional proto classes are absent.
-keep public interface com.google.mediapipe.framework.* { public *; }
-keep public class com.google.mediapipe.framework.Packet {
    public static *** create(***);
    public long getNativeHandle();
    public void release();
}
-keep public class com.google.mediapipe.framework.PacketCreator {
    *** releaseWithSyncToken(...);
}
-keep public class com.google.mediapipe.framework.MediaPipeException {
    <init>(int, byte[]);
}
-keep class com.google.mediapipe.framework.ProtoUtil$SerializedMessage { *; }

# Protobuf-lite's MessageSchema resolves generated fields by their encoded names.
# The pinned SDK has no consumer rule for this. Removing e.g. SystemInfo's
# hostEnvironment_ makes model initialisation fail before any hand sample runs.
-keepclassmembers class * extends com.google.protobuf.GeneratedMessageLite {
    <fields>;
}
