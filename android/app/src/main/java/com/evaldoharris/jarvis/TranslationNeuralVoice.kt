package com.evaldoharris.jarvis

import android.content.Context
import com.k2fsa.sherpa.onnx.OfflineTts
import com.k2fsa.sherpa.onnx.OfflineTtsConfig
import com.k2fsa.sherpa.onnx.OfflineTtsModelConfig
import com.k2fsa.sherpa.onnx.OfflineTtsVitsModelConfig
import java.io.File

/** Same Brazilian male Piper voice family as the PC, entirely on-device. */
class TranslationNeuralVoice(context: Context) : AutoCloseable {
    // JNI expects invoke(float[]): Integer. Kotlin's invokedynamic lambdas expose
    // only invoke(Object), so use a real Function1 class with the typed bridge.
    private class CancellationCallback(private val cancelled:()->Boolean):(FloatArray)->Int {
        override fun invoke(samples:FloatArray):Int = if(cancelled())0 else 1
    }
    private val model: OfflineTts
    init {
        val name="vits-piper-pt_BR-faber-medium-int8"
        val root=File(context.filesDir,"translation-neural-faber-v1")
        val marker=File(root,"READY")
        if(!marker.isFile) {
            copy(context,"translation-voice/$name",root)
            marker.writeText("1")
        }
        model=OfflineTts(config=OfflineTtsConfig(model=OfflineTtsModelConfig(
            vits=OfflineTtsVitsModelConfig(model=File(root,"pt_BR-faber-medium.onnx").absolutePath,
                tokens=File(root,"tokens.txt").absolutePath,dataDir=File(root,"espeak-ng-data").absolutePath),numThreads=2)))
    }
    private fun copy(context:Context,path:String,target:File) {
        check(!Thread.currentThread().isInterrupted) { "Carregamento de voz cancelado" }
        val entries=context.assets.list(path).orEmpty()
        if(entries.isEmpty()) {
            target.parentFile?.mkdirs()
            context.assets.open(path).use { source -> target.outputStream().use { source.copyTo(it) } }
        } else { target.mkdirs();for(entry in entries)copy(context,"$path/$entry",File(target,entry)) }
    }
    fun synthesize(text:String,output:File,cancelled:()->Boolean):Boolean {
        if(cancelled())return false
        val generated=model.generateWithCallback(text=text,sid=0,speed=1.05f,callback=CancellationCallback(cancelled))
        if(cancelled())return false
        check(generated.samples.isNotEmpty()) { "A voz neural não gerou áudio" }
        TranslationPcm.writeWav(TranslationPcm.normalized(generated.samples),generated.sampleRate,output)
        return true
    }
    override fun close() { model.release() }
}
