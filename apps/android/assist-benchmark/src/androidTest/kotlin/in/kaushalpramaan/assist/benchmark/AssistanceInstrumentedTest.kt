package `in`.kaushalpramaan.assist.benchmark

import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Color
import androidx.exifinterface.media.ExifInterface
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import `in`.kaushalpramaan.assist.quality.*
import `in`.kaushalpramaan.assist.hands.*
import java.io.File
import java.security.MessageDigest
import java.util.Base64
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AssistanceInstrumentedTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext
    private val root get() = File(context.cacheDir, "assistance-instrumentation").apply { mkdirs() }
    private fun fixture(name: String): File = File(root, name).also { file ->
        instrumentation.context.assets.open("fixtures/$name").use { input -> file.outputStream().use { input.copyTo(it) } }
    }
    private fun quality() = QualityAnalyzer(QualityThresholds.bundled(context))

    @Test fun bundledAssetDigestAndOfflinePermissionBoundary() {
        val metadata = context.assets.open("hands/model.json").use { JSONObject(it.readBytes().toString(Charsets.UTF_8)) }
        val digest = MessageDigest.getInstance("SHA-256")
        context.assets.open(metadata.getString("asset")).use { input -> val b = ByteArray(65536)
            while (true) { val n = input.read(b); if (n < 0) break; digest.update(b, 0, n) } }
        assertEquals(metadata.getString("sha256"), digest.digest().joinToString("") { "%02x".format(it) })
        val permissions = context.packageManager.getPackageInfo(context.packageName, PackageManager.GET_PERMISSIONS).requestedPermissions.orEmpty()
        assertFalse(permissions.contains("android.permission.INTERNET"))
        assertFalse(permissions.any { it.contains("EXTERNAL_STORAGE") || it.contains("READ_MEDIA") })
    }

    @Test fun allEightExifOrientationsHaveCorrectPixelsAspectAndBoundedDecode() {
        val original = Bitmap.createBitmap(1024, 640, Bitmap.Config.ARGB_8888)
        for (y in 0 until 640) for (x in 0 until 1024) original.setPixel(x, y,
            if (y < 320) { if (x < 512) Color.RED else Color.GREEN } else { if (x < 512) Color.BLUE else Color.WHITE })
        val expected = listOf(listOf(Color.RED, Color.GREEN, Color.BLUE, Color.WHITE),
            listOf(Color.GREEN, Color.RED, Color.WHITE, Color.BLUE), listOf(Color.WHITE, Color.BLUE, Color.GREEN, Color.RED),
            listOf(Color.BLUE, Color.WHITE, Color.RED, Color.GREEN), listOf(Color.RED, Color.BLUE, Color.GREEN, Color.WHITE),
            listOf(Color.BLUE, Color.RED, Color.WHITE, Color.GREEN), listOf(Color.WHITE, Color.GREEN, Color.BLUE, Color.RED),
            listOf(Color.GREEN, Color.WHITE, Color.RED, Color.BLUE))
        try {
            for (orientation in 1..8) {
                val file = File(root, "orientation-$orientation.jpg")
                file.outputStream().use { assertTrue(original.compress(Bitmap.CompressFormat.JPEG, 100, it)) }
                ExifInterface(file).apply { setAttribute(ExifInterface.TAG_ORIENTATION, orientation.toString()); saveAttributes() }
                val decoded = BoundedMedia.photo(file)
                try {
                    assertEquals(320, maxOf(decoded.width, decoded.height))
                    assertEquals(if (orientation <= 4) 320 else 200, decoded.width)
                    assertEquals(if (orientation <= 4) 200 else 320, decoded.height)
                    val points = listOf(8 to 8, decoded.width - 9 to 8, 8 to decoded.height - 9, decoded.width - 9 to decoded.height - 9)
                    for ((i, point) in points.withIndex()) {
                        val actual = decoded.getPixel(point.first, point.second); val wanted = expected[orientation - 1][i]
                        assertTrue("orientation=$orientation corner=$i", kotlin.math.abs(Color.red(actual) - Color.red(wanted)) < 15 &&
                            kotlin.math.abs(Color.green(actual) - Color.green(wanted)) < 15 && kotlin.math.abs(Color.blue(actual) - Color.blue(wanted)) < 15)
                    }
                } finally { decoded.recycle() }
            }
        } finally { original.recycle() }
    }

    @Test fun realAndroidMetricsMatchIndependentGoldenVectors() {
        val lines = instrumentation.context.assets.open("golden_metrics.tsv").bufferedReader().use { it.readLines().drop(1) }
        assertEquals(16, lines.size)
        for (line in lines) {
            val c = line.split('\t')
            val m = QualityMetrics.calculate(GrayFrame(c[1].toInt(), c[2].toInt(), Base64.getDecoder().decode(c[3])))
            assertEquals(c[4].toDouble(), m.meanLuma, 1e-9); assertEquals(c[5].toDouble(), m.darkClipFraction, 1e-9)
            assertEquals(c[6].toDouble(), m.highlightClipFraction, 1e-9)
            if (c[7] == "None") assertNull(m.laplacianVariance) else assertEquals(c[7].toDouble(), m.laplacianVariance!!, 1e-6)
        }
    }

    @Test fun videoRotationIsBakedExactlyOnceAndFramesStayBounded() {
        for (sequential in listOf(false, true)) {
            val base = VideoFrames(fixture("synthetic-landscape.mp4"), sequential).use { it.frame(500)!! }
            try {
                for (name in listOf("synthetic-landscape.mp4", "synthetic-rotation90.mp4")) VideoFrames(fixture(name), sequential).use { source ->
                    val frame = source.frame(500) ?: error("Missing video frame")
                    val expected = BoundedMedia.orient(base, when (source.info.rotationDegrees) { 90 -> 6; 180 -> 3; 270 -> 8; else -> 1 })
                    try {
                        assertTrue(maxOf(frame.width, frame.height) <= 320)
                        assertEquals(source.info.displayWidth.toDouble() / source.info.displayHeight,
                            frame.width.toDouble() / frame.height, 0.02)
                        assertEquals(expected.width, frame.width); assertEquals(expected.height, frame.height)
                        var difference = 0L; var channels = 0
                        for (y in 8 until frame.height step 13) for (x in 8 until frame.width step 13) {
                            val a = frame.getPixel(x, y); val b = expected.getPixel(x, y)
                            difference += kotlin.math.abs(Color.red(a) - Color.red(b)) + kotlin.math.abs(Color.green(a) - Color.green(b)) + kotlin.math.abs(Color.blue(a) - Color.blue(b))
                            channels += 3
                        }
                        assertTrue("Rotated video pixels differ: sequential=$sequential", difference.toDouble() / channels < 8)
                    } finally { frame.recycle(); if (expected !== base) expected.recycle() }
                }
            } finally { base.recycle() }
        }
    }

    @Test fun corruptInputsFailExplicitlyAndNeverBecomeNoHands() = runBlocking {
        val file = File(root, "corrupt.bin").apply { writeText("not an image or video") }
        assertEquals(AnalysisStatus.UNAVAILABLE, QualityAnalyzer(null).photo(file).status)
        assertEquals(AnalysisStatus.UNAVAILABLE, QualityAnalyzer(null).video(file).status)
        assertEquals(AnalysisStatus.FAILED, quality().photo(file).status)
        assertEquals(AnalysisStatus.FAILED, quality().video(file).status)
        val hands = HandsAnalyzer(context).video(file)
        assertEquals(AnalysisStatus.FAILED, hands.status); assertNull(hands.summary.visibleRatio)
        assertTrue(hands.summary.handsNotVisibleIntervals.isEmpty())
    }

    @Test fun tinyPhotoIsUnjudgeableAndRepeatedBlankPhotoRunsReleaseModels() = runBlocking {
        val tiny = File(root, "tiny.png")
        Bitmap.createBitmap(2, 1, Bitmap.Config.ARGB_8888).let { bitmap ->
            tiny.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }; bitmap.recycle() }
        val tinyResult = HandsAnalyzer(context).photo(tiny)
        assertEquals(1, tinyResult.summary.unjudgeableCount); assertNull(tinyResult.summary.visibleRatio)
        val tinyQuality = quality().photo(tiny)
        assertEquals(AnalysisStatus.PARTIAL, tinyQuality.status)
        assertEquals("blur_unavailable", tinyQuality.error)
        assertNull(tinyQuality.samples.single().metrics!!.laplacianVariance)
        val blank = File(root, "blank.png")
        Bitmap.createBitmap(320, 180, Bitmap.Config.ARGB_8888).let { bitmap -> bitmap.eraseColor(Color.WHITE)
            blank.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }; bitmap.recycle() }
        assertTrue("Accepted instrumentation requires actual bundled calibration", QualityThresholds.bundled(context).calibrated)
        val saturation = quality().photo(blank)
        assertEquals(AnalysisStatus.SUCCESS, saturation.status)
        assertTrue(saturation.samples.single().flags.any { it.condition == QualityCondition.OVEREXPOSED })
        val black = File(root, "black.png")
        Bitmap.createBitmap(320, 180, Bitmap.Config.ARGB_8888).let { bitmap -> bitmap.eraseColor(Color.BLACK)
            black.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }; bitmap.recycle() }
        assertEquals(listOf(QualityCondition.DARK), quality().photo(black).samples.single().flags.map { it.condition })
        repeat(3) {
            val result = HandsAnalyzer(context).photo(blank)
            assertEquals(AnalysisStatus.SUCCESS, result.status)
            assertEquals(0, result.samples.single().handCount)
            assertEquals(0.0, result.summary.visibleRatio!!, 0.0)
        }
    }

    @Test fun cancellationAfterActualVideoSamplesReleasesReadersAndNativeEngine() = runBlocking {
        withTimeout(60000) {
            val video = fixture("synthetic-landscape.mp4")
            var qualityObserved = 0
            lateinit var q: Job
            q = launch(start = CoroutineStart.LAZY) { quality().video(video) { qualityObserved++; q.cancel() } }
            q.start(); q.join(); assertTrue(q.isCancelled); assertEquals(1, qualityObserved)
            assertTrue(quality().video(video).samples.isNotEmpty())
            var handsObserved = 0
            lateinit var h: Job
            h = launch(start = CoroutineStart.LAZY) { HandsAnalyzer(context).video(video) { handsObserved++; h.cancel() } }
            h.start(); h.join(); assertTrue(h.isCancelled); assertEquals(1, handsObserved)
            val rerun = HandsAnalyzer(context).video(video)
            assertEquals(AnalysisStatus.SUCCESS, rerun.status)
            assertEquals(listOf(0L, 1000L), rerun.samples.map { it.timestampMs })
        }
    }
}
