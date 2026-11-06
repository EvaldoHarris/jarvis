package com.evaldoharris.jarvis

import android.content.Context
import android.media.MediaPlayer
import android.media.PlaybackParams
import android.os.SystemClock
import java.io.File
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

/** Synthesize the next phrase while playing the current one; preserve ordered speech. */
class TranslationNarrator(private val context:Context,private val report:(String)->Unit) {
    private data class Request(val text:String,val created:Long,val generation:Int)
    private data class Prepared(val request:Request,val file:File)
    private val stop=AtomicBoolean(false)
    private val generation=AtomicInteger(0)
    private val pending=LinkedBlockingQueue<Request>(64)
    private val ready=LinkedBlockingQueue<Prepared>(2)
    private val synthesis=Executors.newSingleThreadExecutor()
    private val playback=Executors.newSingleThreadExecutor()
    @Volatile private var enabled=true
    @Volatile private var volume=SecureStore(context).get("translation_volume","100").toIntOrNull()?.coerceIn(0,100)?.div(100f)?:1f
    internal val preparedCount get()=ready.size
    private fun cancelled(request:Request)=stop.get()||!enabled||request.generation!=generation.get()
    private fun paused()=AppState.audioBusy||System.currentTimeMillis()<VideoTranslationState.pauseNarrationUntil
    init {
        synthesis.execute {
            var voice:TranslationNeuralVoice?=null
            try {
                voice=TranslationNeuralVoice(context)
                while(!stop.get()) {
                    val request=pending.poll(100,TimeUnit.MILLISECONDS)?:continue
                    if(cancelled(request))continue
                    val file=File.createTempFile("translation-",".wav",context.cacheDir)
                    var handedOff=false
                    try {
                        if(!voice.synthesize(request.text,file){cancelled(request)})continue
                        while(!cancelled(request)) {
                            synchronized(this) {
                                if(!cancelled(request))handedOff=ready.offer(Prepared(request,file))
                            }
                            if(handedOff)break
                            Thread.sleep(25)
                        }
                    } finally { if(!handedOff)file.delete() }
                }
            } catch(_:InterruptedException){} catch(e:Exception){failed(e)}
            finally { voice?.close() }
        }
        playback.execute {
            try {
                while(!stop.get()) {
                    val item=ready.poll(100,TimeUnit.MILLISECONDS)?:continue
                    try { play(item) } finally { item.file.delete() }
                }
            } catch(_:InterruptedException){} catch(e:Exception){failed(e)}
        }
    }
    private fun play(item:Prepared) {
        val request=item.request
        while(!cancelled(request)&&paused())Thread.sleep(25)
        if(cancelled(request))return
        val audio=MediaPlayer()
        try {
            audio.setAudioAttributes(AssistantAudio.attributes())
            audio.setDataSource(item.file.absolutePath);audio.prepare()
            if(cancelled(request))return
            var applied=volume;audio.setVolume(applied,applied)
            var rate=TranslationPacing.speed(SystemClock.elapsedRealtime()-request.created,pending.size+ready.size)
            audio.playbackParams=PlaybackParams().setSpeed(rate).setPitch(1f)
            VideoTranslationState.spokenText=request.text;VideoTranslationState.speaking=true
            audio.start()
            while(!cancelled(request)&&audio.isPlaying) {
                if(paused()) {
                    audio.pause();VideoTranslationState.speaking=false
                    while(!cancelled(request)&&paused())Thread.sleep(25)
                    if(!cancelled(request)){VideoTranslationState.speaking=true;audio.start()}
                }
                if(volume!=applied){applied=volume;audio.setVolume(applied,applied)}
                val nextRate=TranslationPacing.speed(SystemClock.elapsedRealtime()-request.created,pending.size+ready.size)
                if(nextRate>rate&&pending.size+ready.size>0) {
                    rate=nextRate;audio.playbackParams=PlaybackParams().setSpeed(rate).setPitch(1f)
                }
                Thread.sleep(25)
            }
        } finally {
            VideoTranslationState.lastNarrationEnd=System.currentTimeMillis()
            VideoTranslationState.speaking=false;audio.release()
        }
    }
    private fun failed(e:Exception) {
        if(!stop.get()) {
            setAudio(false)
            report("Áudio desativado: ${e.message}. As legendas continuam.")
        }
    }
    @Synchronized fun offer(text:String) {
        if(stop.get()||!enabled||text.isBlank())return
        if(!pending.offer(Request(text,SystemClock.elapsedRealtime(),generation.get()))) {
            setAudio(false)
            report("A voz não acompanhou o vídeo. Pause o vídeo e reative o áudio; as legendas continuam.")
        }
    }
    @Synchronized fun setAudio(value:Boolean) {
        enabled=value
        if(!value) {
            generation.incrementAndGet();pending.clear()
            while(true){val item=ready.poll()?:break;item.file.delete()}
        }
    }
    fun setVolume(percent:Int){volume=percent.coerceIn(0,100)/100f}
    fun close(){stop.set(true);setAudio(false);synthesis.shutdownNow();playback.shutdownNow()}
}
