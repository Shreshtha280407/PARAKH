package `in`.kaushalpramaan.assist.quality
import org.junit.Assert.*
import org.junit.Test

class YuvToRgbTest {
    /** Direct re-implementation of the original per-pixel formula [YuvToRgb] replaces,
     * kept independent of it so this test cannot pass by sharing a bug with production code. */
    private fun reference(standard: ColorStandard, fullRange: Boolean, y: Int, u: Int, v: Int): Int {
        val bt709 = standard == ColorStandard.BT709
        val bt2020 = standard == ColorStandard.BT2020
        val rv = if (fullRange) { if (bt709) 403 else if (bt2020) 377 else 359 } else { if (bt709) 459 else if (bt2020) 430 else 409 }
        val gu = if (fullRange) { if (bt709) 48 else if (bt2020) 42 else 88 } else { if (bt709) 55 else if (bt2020) 48 else 100 }
        val gv = if (fullRange) { if (bt709) 120 else if (bt2020) 146 else 183 } else { if (bt709) 136 else if (bt2020) 167 else 208 }
        val bu = if (fullRange) { if (bt709) 475 else if (bt2020) 482 else 454 } else { if (bt709) 541 else if (bt2020) 548 else 516 }
        val su = u - 128; val sv = v - 128
        val yy = if (fullRange) 256 * y else 298 * (y - 16)
        val r = ((yy + rv * sv + 128) shr 8).coerceIn(0, 255)
        val g = ((yy - gu * su - gv * sv + 128) shr 8).coerceIn(0, 255)
        val b = ((yy + bu * su + 128) shr 8).coerceIn(0, 255)
        return (255 shl 24) or (r shl 16) or (g shl 8) or b
    }

    @Test fun matchesTheOriginalFormulaAcrossAllStandardsRangesAndChannelExtremes() {
        val samples = listOf(0, 1, 16, 17, 55, 100, 127, 128, 129, 200, 234, 235, 254, 255)
        for (standard in ColorStandard.entries) for (fullRange in listOf(false, true)) {
            val table = YuvToRgb(standard, fullRange)
            for (y in samples) for (u in samples) for (v in samples) {
                assertEquals("standard=$standard fullRange=$fullRange y=$y u=$u v=$v",
                    reference(standard, fullRange, y, u, v), table.argb(y, u, v))
            }
        }
    }

    @Test fun alphaChannelIsAlwaysOpaque() {
        assertEquals(255, (YuvToRgb(ColorStandard.BT601, false).argb(128, 128, 128) ushr 24) and 255)
    }
}
