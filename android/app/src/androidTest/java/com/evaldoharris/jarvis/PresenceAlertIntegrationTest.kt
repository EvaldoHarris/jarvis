package com.evaldoharris.jarvis

import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.drawable.BitmapDrawable
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream

@RunWith(AndroidJUnit4::class)
class PresenceAlertIntegrationTest {
    private val instrument = InstrumentationRegistry.getInstrumentation()
    private val context = instrument.targetContext
    private val alertId = "alert_" + "a".repeat(24)
    private fun jpeg(color: Int): ByteArray {
        val bitmap = Bitmap.createBitmap(160, 120, Bitmap.Config.ARGB_8888)
        bitmap.eraseColor(color)
        return ByteArrayOutputStream().use { out -> bitmap.compress(Bitmap.CompressFormat.JPEG, 90, out); bitmap.recycle(); out.toByteArray() }
    }
    private fun descendants(view: View): List<View> = listOf(view) + if (view is ViewGroup)
        (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()
    @Test fun receivedFramesRenderInPreviewAndOldStreamsCannotReplaceThem() {
        PresencePreviewState.clear()
        assertTrue(PresencePreviewState.receive(alertId, jpeg(Color.GREEN), true, false))
        val activity = instrument.startActivitySync(Intent(context, PresenceAlertActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        try {
            instrument.waitForIdleSync()
            instrument.runOnMainSync {
                val image = descendants(activity.findViewById(android.R.id.content)).filterIsInstance<ImageView>().single()
                val bitmap = (image.drawable as BitmapDrawable).bitmap
                assertTrue(Color.green(bitmap.getPixel(0, 0)) > 200)
            }
            assertFalse(PresencePreviewState.receive("alert_" + "b".repeat(24), jpeg(Color.RED), false, false))
            assertTrue(PresencePreviewState.receive(alertId, jpeg(Color.BLUE), false, false))
            instrument.waitForIdleSync()
            instrument.runOnMainSync {
                val image = descendants(activity.findViewById(android.R.id.content)).filterIsInstance<ImageView>().single()
                assertTrue(Color.blue((image.drawable as BitmapDrawable).bitmap.getPixel(0, 0)) > 200)
            }
            assertTrue(PresencePreviewState.receive(alertId, byteArrayOf(), false, true))
            instrument.waitForIdleSync()
            instrument.runOnMainSync {
                assertTrue(descendants(activity.findViewById(android.R.id.content)).filterIsInstance<TextView>().any { it.text.contains("prévia encerrada") })
            }
        } finally { PresencePreviewState.clear(); instrument.runOnMainSync { activity.finish() } }
    }
    @Test fun localWarningCompletesBeforePcAudioWithoutGeminiKey() {
        val store = SecureStore(context); val previous = store.get("gemini_key")
        store.put("gemini_key", "")
        val audio = PresencePhoneAudio(context)
        try {
            audio.warning()
            audio.audio("presence_" + "b".repeat(24), ByteArray(4800), 24000)
            audio.finish("presence_" + "b".repeat(24))
            val deadline = System.currentTimeMillis() + 90000
            while (audio.playedStreams == 0 && audio.lastError.isEmpty() && System.currentTimeMillis() < deadline) Thread.sleep(50)
            assertEquals("Offline warning failed: ${audio.lastError}", 1, audio.playedWarnings)
            assertEquals("PC PCM did not drain: ${audio.lastError}", 1, audio.playedStreams)
        } finally { audio.close(); store.put("gemini_key", previous) }
    }
}
