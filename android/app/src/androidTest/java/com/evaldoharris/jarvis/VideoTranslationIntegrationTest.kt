package com.evaldoharris.jarvis

import android.content.Intent
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.nl.translate.Translation
import com.google.mlkit.nl.translate.TranslatorOptions
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.vosk.Model
import org.vosk.Recognizer
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/** Uses only a synthetic English fixture. Initial model setup downloads public models. */
@RunWith(AndroidJUnit4::class)
class VideoTranslationIntegrationTest {
    private val instrument = InstrumentationRegistry.getInstrumentation()
    private val context = instrument.targetContext

    @Test fun continuousSentenceKeepsTheSameWordsAsUninterruptedRecognition() {
        val wav=instrument.context.assets.open("translation_en.wav").use { it.readBytes() }
        assertTrue("Fixture must cross the former 2.5 second reset",wav.size>80044)
        Model(TranslationModels.path(context).absolutePath).use { model ->
            fun decode(accept:(ByteArray)->String?,finish:()->String):String {
                val parts=mutableListOf<String>()
                var offset=44
                while(offset<wav.size) {
                    val end=minOf(offset+3200,wav.size)
                    accept(wav.copyOfRange(offset,end))?.let(parts::add);offset=end
                }
                parts.add(finish());return parts.filter { it.isNotBlank() }.joinToString(" ")
            }
            val expected=Recognizer(model,16000f).use { rec ->
                decode({ b->if(rec.acceptWaveForm(b,b.size))JSONObject(rec.result).optString("text") else null },{JSONObject(rec.finalResult).optString("text")})
            }
            val actual=TranslationRecognizer(model).use { rec -> decode({rec.accept(it,it.size)},{rec.finish()}) }
            android.util.Log.i("JarvisTranslationQA","continuous_sentence=$actual")
            assertTrue(actual.contains("computer"));assertEquals(expected,actual)
        }
    }

    @Test fun narrationRetainsEveryQueuedPhraseAfterFiveSecondsAndResumesAfterInterruption() {
        val oldBusy=AppState.audioBusy;val oldPause=VideoTranslationState.pauseNarrationUntil
        val errors=java.util.concurrent.CopyOnWriteArrayList<String>()
        var narrator:TranslationNarrator?=null
        fun waitFor(condition:()->Boolean) {
            val deadline=System.currentTimeMillis()+30000
            while(!condition()&&errors.isEmpty()&&System.currentTimeMillis()<deadline)Thread.sleep(25)
            assertTrue("Narration failure: $errors",errors.isEmpty());assertTrue("Narration timed out",condition())
        }
        try {
            AppState.audioBusy=true;VideoTranslationState.pauseNarrationUntil=0
            narrator=TranslationNarrator(context){errors.add(it)}
            val phrases=listOf("Primeira frase: o computador precisa permanecer ligado durante a atualização.","Segunda frase: aguarde a conclusão.","Terceira frase: agora terminou.")
            phrases.forEach { narrator.offer(it) }
            Thread.sleep(5500)
            waitFor{narrator.preparedCount>=1}
            val resumed=android.os.SystemClock.elapsedRealtime();AppState.audioBusy=false
            waitFor{VideoTranslationState.speaking&&VideoTranslationState.spokenText==phrases[0]}
            val initialDelay=android.os.SystemClock.elapsedRealtime()-resumed
            assertTrue("Prepared voice should start without a new synthesis: $initialDelay ms",initialDelay<600)
            AppState.audioBusy=true
            waitFor{!VideoTranslationState.speaking}
            Thread.sleep(300)
            assertEquals(phrases[0],VideoTranslationState.spokenText)
            AppState.audioBusy=false
            waitFor{VideoTranslationState.speaking&&VideoTranslationState.spokenText==phrases[0]}
            for(phrase in phrases.drop(1)) {
                waitFor{VideoTranslationState.speaking&&VideoTranslationState.spokenText==phrase}
                val gap=System.currentTimeMillis()-VideoTranslationState.lastNarrationEnd
                android.util.Log.i("JarvisTranslationQA","pipelined_voice_gap_ms=$gap initial_resume_ms=$initialDelay")
                assertTrue("Pre-generated voice must not accumulate synthesis gaps: $gap ms",gap<600)
            }
            waitFor{!VideoTranslationState.speaking}
        } finally {
            narrator?.close();AppState.audioBusy=oldBusy;VideoTranslationState.pauseNarrationUntil=oldPause
        }
    }

    @Test fun recognizesAndTranslatesSyntheticVideoLocally() {
        TranslationModels.prepare(context) { }
        assertTrue(TranslationModels.ready(context))
        val wav = instrument.context.assets.open("translation_en.wav").use { it.readBytes() }
        assertEquals("RIFF", String(wav.copyOfRange(0,4), Charsets.US_ASCII))
        assertEquals("data", String(wav.copyOfRange(36,40), Charsets.US_ASCII))
        val recognized = Model(TranslationModels.path(context).absolutePath).use { model ->
            Recognizer(model, 16000f).use { rec ->
                val parts = mutableListOf<String>()
                var offset=44
                while(offset<wav.size) {
                    val end=minOf(offset+3200,wav.size);val block=wav.copyOfRange(offset,end)
                    if(rec.acceptWaveForm(block,block.size))parts.add(JSONObject(rec.result).optString("text"))
                    offset=end
                }
                parts.add(JSONObject(rec.finalResult).optString("text"));parts.joinToString(" ")
            }
        }
        assertTrue("Recognition: $recognized", recognized.contains("computer"))
        Translation.getClient(TranslatorOptions.Builder().setSourceLanguage("en").setTargetLanguage("pt").build()).use { translator ->
            val text = Tasks.await(translator.translate(recognized), 30, TimeUnit.SECONDS)
            assertTrue("Translation: $text", text.lowercase().contains("computador"))
        }
    }

    @Test fun offlinePortugueseVoiceProducesAndPlaysAudioWithoutCloudVoice() {
        val output = File(context.cacheDir, "qa-translation-voice.wav")
        try {
            TranslationNeuralVoice(context).use { voice ->
                assertFalse(voice.synthesize("Cancelado",output){true})
                assertFalse(output.exists())
                val start=android.os.SystemClock.elapsedRealtime()
                assertTrue(voice.synthesize("Olá. Esta é a voz neural masculina da tradução do Jarvis.",output){false})
                android.util.Log.i("JarvisTranslationQA","neural_synthesis_ms=${android.os.SystemClock.elapsedRealtime()-start} wav_bytes=${output.length()}")
            }
            assertTrue(output.length()>44)
            val complete=CountDownLatch(1)
            val player=MediaPlayer()
            try {
                val attributes=AssistantAudio.attributes()
                assertEquals(AudioAttributes.USAGE_ASSISTANT,attributes.usage)
                assertEquals(AudioAttributes.ALLOW_CAPTURE_BY_NONE,attributes.allowedCapturePolicy)
                player.setAudioAttributes(attributes)
                player.setDataSource(output.absolutePath);player.prepare()
                player.setOnCompletionListener { complete.countDown() };player.start()
                assertTrue(complete.await(12,TimeUnit.SECONDS))
            } finally { player.release() }
        } finally { output.delete() }
    }

    @Test fun wakeTranslationCommandOpensConsentFlowInsteadOfSendingToPc() {
        val host=instrument.startActivitySync(Intent(context,VideoTranslationActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        try {
            val command=WakePhrase().command("Jarvis, ative a tradução","wake",System.currentTimeMillis())
            assertEquals("start",TranslationPolicy.command(command.orEmpty()))
            instrument.runOnMainSync { FeatureTools.videoTranslation(context,TranslationPolicy.command(command.orEmpty())!!) }
            val received=java.util.concurrent.atomic.AtomicBoolean(false)
            val deadline=System.currentTimeMillis()+6000
            while(!received.get()&&System.currentTimeMillis()<deadline) {
                instrument.runOnMainSync { received.set(host.intent.getBooleanExtra("start_translation",false)) }
                if(!received.get())Thread.sleep(100)
            }
            assertTrue("Voice route did not reach the already-open translation page",received.get())
            assertFalse("Capture must wait for Android consent",VideoTranslationState.active)
        } finally {
            // Dismiss any permission/consent dialog. No real application audio is captured.
            runCatching { instrument.sendKeyDownUpSync(android.view.KeyEvent.KEYCODE_BACK) }
            instrument.runOnMainSync { host.finish() }
            context.getSystemService(android.app.NotificationManager::class.java).cancel(32)
        }
    }

    @Test fun translationUiExplainsConsentAndDoesNotStartCaptureByOpening() {
        val activity = instrument.startActivitySync(Intent(context,VideoTranslationActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        try {
            assertFalse(VideoTranslationState.active)
            instrument.waitForIdleSync()
            val image=instrument.getUiAutomation(android.app.UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES).takeScreenshot()
            File(context.cacheDir,"qa-video-translation.png").outputStream().use { image.compress(android.graphics.Bitmap.CompressFormat.PNG,100,it) }
            image.recycle()
        }
        finally { instrument.runOnMainSync { activity.finish() } }
    }
}
