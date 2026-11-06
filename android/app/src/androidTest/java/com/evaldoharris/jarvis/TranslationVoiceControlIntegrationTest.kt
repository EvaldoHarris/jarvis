package com.evaldoharris.jarvis

import android.content.Intent
import android.media.AudioAttributes
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.vosk.Recognizer

@RunWith(AndroidJUnit4::class)
class TranslationVoiceControlIntegrationTest {
    private val instrument=InstrumentationRegistry.getInstrumentation()
    private val context=instrument.targetContext

    @Test fun translationUsesAssistantVolumeCategory() {
        val assistant=AssistantAudio.attributes()
        val media=AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).build()
        assertEquals(AudioAttributes.USAGE_ASSISTANT,assistant.usage)
        assertEquals(AudioAttributes.ALLOW_CAPTURE_BY_NONE,assistant.allowedCapturePolicy)
        android.util.Log.i("JarvisTranslationQA","assistant_volume_stream=${assistant.volumeControlStream} media_volume_stream=${media.volumeControlStream}")
    }
    @Test fun recognizesRecordedSyntheticWakeAndStopEntirelyLocally() {
        WakeSpotter.preload(context)
        val deadline=System.currentTimeMillis()+15000
        while(WakeSpotter.sharedModel()==null&&System.currentTimeMillis()<deadline)Thread.sleep(50)
        val model=WakeSpotter.sharedModel()?:error("Vosk model not ready")
        val wav=instrument.context.assets.open("translation_stop_pt.wav").use { it.readBytes() }
        var accepted=false
        fun inspect(raw:String) {
            val json=JSONObject(raw);val words=json.optJSONArray("result")?:return
            if(words.length()==0)return
            val confidence=(0 until words.length()).map { words.getJSONObject(it).optDouble("conf",0.0) }.average()
            accepted=accepted||TranslationStopPolicy.accepts(json.optString("text"),confidence)
            android.util.Log.i("JarvisTranslationQA","synthetic_stop_confidence=$confidence accepted=$accepted text=${json.optString("text")}")
        }
        Recognizer(model,16000f,JSONArray(TranslationStopPolicy.grammar()).toString()).use { rec ->
            rec.setWords(true);var offset=44
            while(offset<wav.size) {
                val end=minOf(offset+3200,wav.size);val block=wav.copyOfRange(offset,end)
                if(rec.acceptWaveForm(block,block.size))inspect(rec.result)
                offset=end
            }
            inspect(rec.finalResult)
        }
        assertTrue("Local recognizer did not understand the synthetic stop command",accepted)
    }
    @Test fun translationKeepsLocalMicrophoneStopListenerWhenAutomaticModeIsOff() {
        val activity=instrument.startActivitySync(Intent(context,VideoTranslationActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        val store=SecureStore(context);val old=store.get("voice_mode","wake");val previous=VideoTranslationState.active
        try {
            store.put("voice_mode","off");VideoTranslationState.active=true
            context.startForegroundService(Intent(context,WakeListeningService::class.java))
            val deadline=System.currentTimeMillis()+15000
            while(WakeListeningService.current?.localStopListening()!=true&&System.currentTimeMillis()<deadline)Thread.sleep(50)
            assertTrue("Local stop listener was not started",WakeListeningService.current?.localStopListening()==true)
        } finally {
            context.stopService(Intent(context,WakeListeningService::class.java));VideoTranslationState.active=previous
            store.put("voice_mode",old);instrument.runOnMainSync { activity.finish() }
        }
    }
}
