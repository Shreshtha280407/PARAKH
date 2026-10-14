package `in`.kaushalpramaan.assist.quality
import java.util.Base64
import org.junit.Assert.*
import org.junit.Test

class GoldenMetricTest {
    @Test fun kotlinMatchesIndependentPythonOnAllPrivacySafeVectors() {
        val input = java.io.File(System.getProperty("quality.golden.file") ?: error("Missing golden vector path")).inputStream()
        val rows = input.bufferedReader().use { it.readLines().drop(1) }
        assertEquals(16, rows.size)
        for (line in rows) {
            val c = line.split('\t')
            val measured = QualityMetrics.calculate(GrayFrame(c[1].toInt(), c[2].toInt(), Base64.getDecoder().decode(c[3])))
            assertEquals(c[0], c[4].toDouble(), measured.meanLuma, 1e-9)
            assertEquals(c[0], c[5].toDouble(), measured.darkClipFraction, 1e-9)
            assertEquals(c[0], c[6].toDouble(), measured.highlightClipFraction, 1e-9)
            if (c[7] == "None") assertNull(measured.laplacianVariance)
            else assertEquals(c[0], c[7].toDouble(), measured.laplacianVariance!!, 1e-6)
        }
    }
}
