package `in`.kaushalpramaan.media

import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import java.io.File
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Real-device-only proof that [VideoOptimizer] drives the actual Media3 Transformer pipeline
 * (real MediaCodec encode/decode) end to end -- Robolectric/the JVM cannot provide real video
 * codecs, the same constraint this codebase already documents for CameraX and SQLCipher (see
 * docs/gates/P4.md). `sample_video.mp4` (bundled as a test asset) is a real, valid 1280x720
 * H.264/AAC MP4 -- not a mock -- so every assertion below is against genuinely
 * encoded/transcoded bytes.
 */
@RunWith(AndroidJUnit4::class)
class VideoOptimizerInstrumentedTest {

    private lateinit var workDir: File
    private lateinit var sourceFile: File
    private val optimizer = VideoOptimizer(ApplicationProvider.getApplicationContext())

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        workDir = File(context.cacheDir, "video_optimizer_test_${System.nanoTime()}").apply { mkdirs() }
        sourceFile = File(workDir, "source.mp4")
        context.assets.open("sample_video.mp4").use { input -> sourceFile.outputStream().use { input.copyTo(it) } }
    }

    @Test
    fun validateContainer_reads_real_duration_and_dimensions_from_a_real_file() {
        val info = optimizer.validateContainer(sourceFile)
        checkNotNull(info)
        assertEquals(1280, info.widthPx)
        assertEquals(720, info.heightPx)
        assertTrue("duration should be close to the real 3s source", info.durationMs in 2_500..3_500)
        assertEquals(sourceFile.length(), info.bytes)
    }

    @Test
    fun validateContainer_returns_null_for_garbage_bytes_rather_than_crashing() {
        val garbage = File(workDir, "garbage.mp4").apply { writeBytes(byteArrayOf(1, 2, 3, 4)) }
        assertEquals(null, optimizer.validateContainer(garbage))
    }

    @Test
    fun fitting_video_is_returned_byte_identical_and_never_re_transcoded() = runBlocking {
        val originalBytes = sourceFile.readBytes()
        val outputDir = File(workDir, "out").apply { mkdirs() }

        val result = optimizer.optimize(sourceFile, targetBytes = sourceFile.length() + 1, outputDir = outputDir)

        check(result is VideoOptimizationResult.KeptAsIs)
        assertEquals(sourceFile.absolutePath, result.file.absolutePath)
        assertTrue(sourceFile.readBytes().contentEquals(originalBytes))
        assertTrue("no transcode output should exist for a fitting video", outputDir.listFiles()?.isEmpty() != false)
    }

    @Test
    fun oversized_video_is_really_transcoded_by_media3_and_fits_the_target() = runBlocking {
        // The 3s source is CBR-encoded at ~8 Mbps (~3 MB); a materially tighter target, still
        // comfortably above the quality floor, forces a real bitrate-reduction optimisation
        // pass that should fit without needing to step down resolution.
        val target = 1_000_000L
        val outputDir = File(workDir, "out").apply { mkdirs() }

        val result = optimizer.optimize(sourceFile, targetBytes = target, outputDir = outputDir)

        check(result is VideoOptimizationResult.Optimized) { "expected a real Optimized result, got $result" }
        assertTrue("real transcoded output must fit the target", result.bytes <= target)
        assertTrue("output file must actually exist with the reported size", result.file.exists())
        assertEquals(result.bytes, result.file.length())
        assertTrue("output must be a genuinely different file than the source", result.file.absolutePath != sourceFile.absolutePath)
        // Re-reading container metadata on the TRANSCODED file proves it is a real, valid,
        // independently-decodable MP4 -- not a truncated/corrupt stub.
        val reread = optimizer.validateContainer(result.file)
        checkNotNull(reread)
        assertTrue(reread.widthPx <= VideoResolutionProfile.HD.targetWidth)
    }

    @Test
    fun deliberately_impossible_target_still_preserves_a_real_recoverable_draft() = runBlocking {
        val outputDir = File(workDir, "out").apply { mkdirs() }
        val result = optimizer.optimize(sourceFile, targetBytes = 500L, outputDir = outputDir)

        check(result is VideoOptimizationResult.QualityFloorExceeded) { "expected QualityFloorExceeded, got $result" }
        assertTrue("the floor attempt must exceed the impossible target", result.bestAttemptBytes > 500L)
        assertTrue("a real recoverable draft file must exist on disk", result.bestAttemptFile.exists())
        assertTrue("the draft must be genuinely decodable, not a corrupt stub", optimizer.validateContainer(result.bestAttemptFile) != null)
    }

    @Test
    fun invalid_container_is_reported_not_crashed_on() = runBlocking {
        val notAVideo = File(workDir, "not_a_video.mp4").apply { writeBytes(ByteArray(64) { it.toByte() }) }
        val outputDir = File(workDir, "out").apply { mkdirs() }
        val result = optimizer.optimize(notAVideo, targetBytes = 10_000L, outputDir = outputDir)
        assertEquals(VideoOptimizationResult.InvalidContainer, result)
        assertFalse(outputDir.listFiles()?.any { it.name.contains("not_a_video") } ?: false)
    }
}
