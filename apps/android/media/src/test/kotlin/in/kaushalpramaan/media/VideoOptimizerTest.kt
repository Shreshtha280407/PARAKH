package `in`.kaushalpramaan.media

import androidx.test.core.app.ApplicationProvider
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** Real Media3 Transformer execution needs a real device codec (see
 * VideoOptimizerInstrumentedTest, media/src/androidTest) -- this class only covers what is
 * safe and meaningful to prove on the JVM: validateContainer()'s graceful failure mode on
 * input that is not a real video at all. */
@RunWith(RobolectricTestRunner::class)
class VideoOptimizerTest {

    private lateinit var tempDir: File
    private val optimizer = VideoOptimizer(ApplicationProvider.getApplicationContext())

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        tempDir = File(context.cacheDir, "video_optimizer_unit_test_${System.nanoTime()}").apply { mkdirs() }
    }

    @Test
    fun validateContainer_returns_null_rather_than_throwing_for_garbage_bytes() {
        val garbage = File(tempDir, "garbage.mp4").apply { writeBytes(byteArrayOf(0, 1, 2, 3, 4, 5)) }
        assertEquals(null, optimizer.validateContainer(garbage))
    }

    @Test
    fun validateContainer_returns_null_for_a_missing_file_rather_than_throwing() {
        val missing = File(tempDir, "does_not_exist.mp4")
        assertEquals(null, optimizer.validateContainer(missing))
    }
}
