package com.evaldoharris.jarvis

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import org.json.JSONArray
import org.json.JSONObject
import org.vosk.Recognizer
import java.util.concurrent.atomic.AtomicBoolean

/** Microphone remains local and recognizes only the wake+stop phrase during translation. */
internal class TranslationVoiceControl(private val context:Context,private val onStop:()->Unit,private val onFailure:()->Unit):AutoCloseable {
    private val closed=AtomicBoolean(false)
    @Volatile private var record:AudioRecord?=null
    @Volatile internal var isListening=false
        private set
    private val worker=Thread({ listen() },"jarvis-translation-stop")
    init { WakeSpotter.preload(context);worker.start() }
    private fun inspect(raw:String) {
        val result=JSONObject(raw);val words=result.optJSONArray("result")?:return
        if(words.length()==0)return
        val confidence=(0 until words.length()).map { words.getJSONObject(it).optDouble("conf",0.0) }.average()
        val narratorOrTail=VideoTranslationState.speaking||System.currentTimeMillis()<VideoTranslationState.lastNarrationEnd+2000
        if(TranslationStopPolicy.accepts(result.optString("text"),confidence,VideoTranslationState.spokenText,narratorOrTail)) {
            if(closed.compareAndSet(false,true))onStop()
        }
    }
    private fun listen() {
        var rec:Recognizer?=null;var audio:AudioRecord?=null;var echo:AcousticEchoCanceler?=null
        try {
            var waits=0
            while(!closed.get()&&WakeSpotter.sharedModel()==null&&waits++<200)Thread.sleep(50)
            if(closed.get())return
            val model=WakeSpotter.sharedModel()?:error("Reconhecimento local indisponível")
            val grammar=JSONArray(TranslationStopPolicy.grammar())
            rec=Recognizer(model,16000f,grammar.toString()).apply { setWords(true) }
            if(context.checkSelfPermission(Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED)error("Permissão de microfone necessária")
            val size=maxOf(6400,AudioRecord.getMinBufferSize(16000,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT))
            audio=AudioRecord.Builder().setAudioSource(MediaRecorder.AudioSource.VOICE_COMMUNICATION)
                .setAudioFormat(AudioFormat.Builder().setSampleRate(16000).setChannelMask(AudioFormat.CHANNEL_IN_MONO).setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
                .setBufferSizeInBytes(size).build()
            record=audio
            check(audio.state==AudioRecord.STATE_INITIALIZED)
            if(AcousticEchoCanceler.isAvailable())echo=runCatching { AcousticEchoCanceler.create(audio.audioSessionId)?.apply { enabled=true } }.getOrNull()
            if(closed.get())return
            audio.startRecording()
            isListening=true
            val buffer=ByteArray(3200);var samples=0
            while(!closed.get()) {
                val count=audio.read(buffer,0,buffer.size)
                if(closed.get())break
                check(count>0)
                if(AppState.audioBusy||AppState.assistantBusy||System.currentTimeMillis()<AppState.lastAudioEnd+450)continue
                samples+=count/2
                if(rec.acceptWaveForm(buffer,count)){inspect(rec.result);samples=0}
                else if(samples>=64000){inspect(rec.finalResult);rec.reset();samples=0}
            }
        } catch(_:InterruptedException){} catch(_:Exception){if(!closed.get())onFailure()}
        finally { isListening=false;record=null;runCatching { audio?.stop() };echo?.release();audio?.release();rec?.close() }
    }
    override fun close(){closed.set(true);runCatching { record?.stop() };worker.interrupt()}
}
