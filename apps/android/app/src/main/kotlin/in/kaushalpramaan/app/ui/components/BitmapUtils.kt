package `in`.kaushalpramaan.app.ui.components

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import java.io.File

/** Downsamples using BitmapFactory.Options.inSampleSize so a large captured photo never
 * gets fully decoded at its native resolution just to show a preview thumbnail -- bounds
 * are read first (inJustDecodeBounds), then exactly one appropriately-sized decode runs. */
fun decodeSampledBitmap(file: File, reqWidth: Int, reqHeight: Int): Bitmap? {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeFile(file.absolutePath, bounds)
    if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null

    var inSampleSize = 1
    val halfHeight = bounds.outHeight / 2
    val halfWidth = bounds.outWidth / 2
    while (halfHeight / inSampleSize >= reqHeight && halfWidth / inSampleSize >= reqWidth) {
        inSampleSize *= 2
    }

    val options = BitmapFactory.Options().apply { this.inSampleSize = inSampleSize }
    return BitmapFactory.decodeFile(file.absolutePath, options)
}
