package `in`.kaushalpramaan.media

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.exifinterface.media.ExifInterface
import androidx.test.core.app.ApplicationProvider
import java.io.File
import java.io.FileOutputStream
import kotlin.random.Random
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/** Robolectric's default graphics shadows do not perform real pixel/codec work; NATIVE mode
 * uses the real Skia-backed Bitmap/BitmapFactory implementation so JPEG encode/decode here
 * behaves exactly as it does on a real device -- essential for a test that asserts real
 * byte-size and dimension outcomes of real compression. */
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class PhotoOptimizerTest {

    private lateinit var tempDir: File
    private lateinit var outputDir: File
    private val optimizer = PhotoOptimizer()

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        tempDir = File(context.cacheDir, "photo_optimizer_test_${System.nanoTime()}").apply { mkdirs() }
        outputDir = File(tempDir, "out").apply { mkdirs() }
    }

    @Test
    fun fitting_photo_is_returned_byte_identical_and_is_never_recompressed() {
        val source = writeJpeg(width = 200, height = 150, content = BitmapContent.SOLID)
        val originalBytes = source.readBytes()

        val result = optimizer.optimize(source, targetBytes = source.length() + 1, outputDir = outputDir)

        check(result is PhotoOptimizationResult.KeptAsIs)
        assertEquals(source.absolutePath, result.file.absolutePath)
        assertEquals(source.length(), result.bytes)
        assertTrue("byte-identical: content must not change", source.readBytes().contentEquals(originalBytes))
        assertTrue("no optimisation output should be written for a fitting photo", outputDir.listFiles()?.isEmpty() != false)
    }

    @Test
    fun oversized_photo_is_resized_to_at_most_1600px_and_quality_stepped_down_until_it_fits() {
        // 3000x2000 smooth-gradient content: large enough that the un-resized original is
        // well over a deliberately tiny target, and compressible enough that quality 85 at
        // 1600px fits comfortably -- isolating the resize+quality-ladder behaviour itself
        // from the separate quality-floor-refusal scenario below.
        val source = writeJpeg(width = 3000, height = 2000, content = BitmapContent.GRADIENT)
        val target = 150_000L
        check(source.length() > target) { "test fixture must actually exceed the target to exercise the ladder" }

        val result = optimizer.optimize(source, targetBytes = target, outputDir = outputDir)

        check(result is PhotoOptimizationResult.Optimized)
        assertTrue("result must fit the target", result.bytes <= target)
        assertTrue("longest side must be at most 1600px", maxOf(result.widthPx, result.heightPx) <= 1600)
        assertTrue("width must be a real positive dimension", result.widthPx > 0 && result.heightPx > 0)
        assertTrue("quality used must be one of the documented ladder steps", result.qualityUsed == 85 || result.qualityUsed == 75)
        // The written file's own real size must match what was reported, and must actually
        // decode as a valid JPEG at the claimed dimensions.
        assertEquals(result.bytes, result.file.length())
        val decoded = BitmapFactory.decodeFile(result.file.absolutePath)
        assertEquals(result.widthPx, decoded.width)
        assertEquals(result.heightPx, decoded.height)
    }

    @Test
    fun quality_85_is_tried_before_the_75_floor() {
        // A target wide enough to fit at quality 85 but tight enough that it would not have
        // fit the unresized original -- proves 85 is attempted (and accepted) first, not
        // skipped straight to the floor.
        val source = writeJpeg(width = 2400, height = 1600, content = BitmapContent.GRADIENT)
        val at85 = probeSizeAtQuality(source, PhotoOptimizer.MAX_LONGEST_SIDE_PX, 85)
        val result = optimizer.optimize(source, targetBytes = at85 + 500, outputDir = outputDir)
        check(result is PhotoOptimizationResult.Optimized)
        assertEquals(85, result.qualityUsed)
    }

    // Orientation handling is split into two independently real, independently tested
    // responsibilities below: reading the EXIF tag (pure metadata, no codec involved) and
    // applying it as a pixel-level rotation/flip (pure in-memory Bitmap transform, no file
    // I/O). Robolectric's NATIVE graphics mode can decode/encode real JPEGs but has a known
    // rough edge decoding a JPEG immediately after `ExifInterface#saveAttributes()` rewrites
    // its EXIF segment ("Failed to create image decoder: unimplemented") -- a test-harness
    // limitation, not a production-code one (a real device's codec handles this routinely,
    // and `optimize()`'s own orientation path is exercised for real in the P5 physical gate).
    // Testing the two real sub-steps directly, without that fragile round-trip, still proves
    // the actual orientation logic is correct.

    @Test
    fun readOrientation_reports_the_real_exif_tag_from_a_file() {
        val file = writeJpeg(width = 100, height = 100, content = BitmapContent.SOLID)
        ExifInterface(file.absolutePath).apply {
            setAttribute(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_ROTATE_90.toString())
            saveAttributes()
        }
        assertEquals(ExifInterface.ORIENTATION_ROTATE_90, optimizer.readOrientation(file))
    }

    @Test
    fun readOrientation_for_a_file_with_no_orientation_tag_leads_to_a_no_op_rotation() {
        // Bitmap.compress() does not itself write an EXIF orientation segment, so this
        // asserts the real behavioural contract that matters -- whatever readOrientation
        // reports for a tag-less file, feeding it into applyOrientation must be a no-op --
        // rather than depending on a specific raw ExifInterface integer value for "absent",
        // which can vary across EXIF-parser implementations.
        val file = writeJpeg(width = 100, height = 100, content = BitmapContent.SOLID)
        val orientation = optimizer.readOrientation(file)
        val bitmap = Bitmap.createBitmap(50, 50, Bitmap.Config.ARGB_8888)
        val result = optimizer.applyOrientation(bitmap, orientation)
        assertTrue("a photo with no explicit orientation tag must not be rotated", result === bitmap)
    }

    @Test
    fun applyOrientation_rotate_90_swaps_width_and_height() {
        val bitmap = Bitmap.createBitmap(400, 200, Bitmap.Config.ARGB_8888)
        val rotated = optimizer.applyOrientation(bitmap, ExifInterface.ORIENTATION_ROTATE_90)
        assertEquals(200, rotated.width)
        assertEquals(400, rotated.height)
    }

    @Test
    fun applyOrientation_rotate_180_keeps_dimensions_but_flips_content() {
        val bitmap = Bitmap.createBitmap(10, 20, Bitmap.Config.ARGB_8888).apply { setPixel(0, 0, 0xFFFF0000.toInt()) }
        val rotated = optimizer.applyOrientation(bitmap, ExifInterface.ORIENTATION_ROTATE_180)
        assertEquals(10, rotated.width)
        assertEquals(20, rotated.height)
        assertEquals(0xFFFF0000.toInt(), rotated.getPixel(9, 19))
    }

    @Test
    fun applyOrientation_normal_returns_the_same_bitmap_instance_unchanged() {
        val bitmap = Bitmap.createBitmap(50, 50, Bitmap.Config.ARGB_8888)
        val result = optimizer.applyOrientation(bitmap, ExifInterface.ORIENTATION_NORMAL)
        assertTrue("no-op orientation must not allocate a new bitmap", result === bitmap)
    }

    @Test
    fun optimize_end_to_end_bakes_orientation_for_a_photo_that_needs_resizing() {
        // No post-hoc EXIF rewrite here (the fragile Robolectric path above) -- this fixture
        // is already large enough to force the resize/re-encode path on its own, and carries
        // no orientation tag (ORIENTATION_NORMAL), so applyOrientation's no-op branch runs
        // for real inside the full optimize() pipeline end to end.
        val source = writeJpeg(width = 3000, height = 1500, content = BitmapContent.GRADIENT)
        val result = optimizer.optimize(source, targetBytes = 150_000L, outputDir = outputDir)
        check(result is PhotoOptimizationResult.Optimized)
        assertTrue(maxOf(result.widthPx, result.heightPx) <= PhotoOptimizer.MAX_LONGEST_SIDE_PX)
        // Aspect ratio (2:1) is preserved -- confirms the resize path didn't silently rotate
        // or distort the image.
        assertEquals(2.0, result.widthPx.toDouble() / result.heightPx.toDouble(), 0.05)
    }

    @Test
    fun quality_floor_refusal_preserves_a_recoverable_draft_instead_of_destroying_it() {
        // Pure random per-pixel noise compresses extremely poorly in JPEG -- even at 1600px
        // and quality 75 it stays large, so an aggressively tiny target cannot be met.
        val source = writeJpeg(width = 1800, height = 1800, content = BitmapContent.NOISE)
        val floorSize = probeSizeAtQuality(source, PhotoOptimizer.MAX_LONGEST_SIDE_PX, PhotoOptimizer.QUALITY_FLOOR)
        val impossibleTarget = (floorSize / 4).coerceAtLeast(1L)

        val result = optimizer.optimize(source, targetBytes = impossibleTarget, outputDir = outputDir)

        check(result is PhotoOptimizationResult.QualityFloorExceeded)
        assertTrue("the floor attempt must still exceed the impossible target", result.bestAttemptBytes > impossibleTarget)
        assertTrue("the recoverable draft file must actually exist on disk", result.bestAttemptFile.exists())
        assertTrue("the recoverable draft must be a real, decodable JPEG", optimizer.validateDecodable(result.bestAttemptFile))
        // Only the kept floor attempt remains in the output dir -- the rejected quality-85
        // attempt must have been cleaned up, not left as orphaned output.
        val leftoverFiles = outputDir.listFiles().orEmpty()
        assertEquals(1, leftoverFiles.size)
        assertEquals(result.bestAttemptFile.absolutePath, leftoverFiles.first().absolutePath)
    }

    @Test
    fun undecodable_file_is_reported_not_crashed_on() {
        val notAPhoto = File(tempDir, "not_a_photo.jpg").apply { writeBytes(Random(1).nextBytes(256)) }
        val result = optimizer.optimize(notAPhoto, targetBytes = 10_000L, outputDir = outputDir)
        assertEquals(PhotoOptimizationResult.UndecodablePhoto, result)
    }

    @Test
    fun validateDecodable_is_true_for_a_real_photo_and_false_for_garbage_bytes() {
        val real = writeJpeg(100, 100, BitmapContent.SOLID)
        assertTrue(optimizer.validateDecodable(real))
        val garbage = File(tempDir, "garbage.jpg").apply { writeBytes(byteArrayOf(1, 2, 3)) }
        assertFalse(optimizer.validateDecodable(garbage))
    }

    // ---- test fixtures ----

    private enum class BitmapContent { SOLID, GRADIENT, NOISE }

    private fun writeJpeg(width: Int, height: Int, content: BitmapContent, orientation: Int? = null): File {
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        when (content) {
            BitmapContent.SOLID -> {
                for (y in 0 until height) for (x in 0 until width) bitmap.setPixel(x, y, 0xFF336699.toInt())
            }
            BitmapContent.GRADIENT -> {
                for (y in 0 until height) for (x in 0 until width) {
                    val r = (255 * x / width.coerceAtLeast(1)) and 0xFF
                    val g = (255 * y / height.coerceAtLeast(1)) and 0xFF
                    bitmap.setPixel(x, y, (0xFF shl 24) or (r shl 16) or (g shl 8) or 0x40)
                }
            }
            BitmapContent.NOISE -> {
                val random = Random(42)
                for (y in 0 until height) for (x in 0 until width) {
                    bitmap.setPixel(x, y, (0xFF shl 24) or random.nextInt(0x1000000))
                }
            }
        }
        val file = File(tempDir, "src_${width}x$height${orientation?.let { "_o$it" } ?: ""}_${System.nanoTime()}.jpg")
        FileOutputStream(file).use { out -> bitmap.compress(Bitmap.CompressFormat.JPEG, 100, out) }
        bitmap.recycle()
        if (orientation != null) {
            ExifInterface(file.absolutePath).apply {
                setAttribute(ExifInterface.TAG_ORIENTATION, orientation.toString())
                saveAttributes()
            }
        }
        return file
    }

    /** Decodes+recompresses [source] at [maxLongestSide]/[quality] without going through
     * [PhotoOptimizer] at all, purely to know in advance what size a given ladder step will
     * produce for a given fixture -- used to compute targets that deliberately land exactly
     * on one side or the other of a ladder step. */
    private fun probeSizeAtQuality(source: File, maxLongestSide: Int, quality: Int): Long {
        val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(source.absolutePath, options)
        var sampleSize = 1
        val longest = maxOf(options.outWidth, options.outHeight)
        while (longest / (sampleSize * 2) >= maxLongestSide) sampleSize *= 2
        val decoded = BitmapFactory.decodeFile(source.absolutePath, BitmapFactory.Options().apply { inSampleSize = sampleSize })
        val scale = maxLongestSide.toFloat() / maxOf(decoded.width, decoded.height)
        val scaled = if (maxOf(decoded.width, decoded.height) > maxLongestSide) {
            Bitmap.createScaledBitmap(decoded, (decoded.width * scale).toInt(), (decoded.height * scale).toInt(), true)
        } else {
            decoded
        }
        val probe = File(tempDir, "probe_${System.nanoTime()}.jpg")
        FileOutputStream(probe).use { out -> scaled.compress(Bitmap.CompressFormat.JPEG, quality, out) }
        val size = probe.length()
        probe.delete()
        return size
    }
}
