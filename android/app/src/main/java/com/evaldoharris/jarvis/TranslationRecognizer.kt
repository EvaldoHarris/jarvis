package com.evaldoharris.jarvis

import org.json.JSONObject
import org.vosk.Model
import org.vosk.Recognizer

/** Keep acoustic/word context until Vosk detects a pause; cap uninterrupted speech at 15 s. */
internal class TranslationRecognizer(model:Model):AutoCloseable {
    private val recognizer=Recognizer(model,16000f).apply {
        // Native endpoints keep decoder context instead of resetting in the middle of a word.
        setEndpointerDelays(5f,0.45f,8f)
    }
    private var samples=0
    fun accept(bytes:ByteArray,count:Int):String? {
        samples+=count/2
        if(recognizer.acceptWaveForm(bytes,count)) {
            samples=0
            return JSONObject(recognizer.result).optString("text").takeIf { it.isNotBlank() }
        }
        if(samples>=240000) {
            val text=JSONObject(recognizer.finalResult).optString("text")
            recognizer.reset();samples=0
            return text.takeIf { it.isNotBlank() }
        }
        return null
    }
    fun finish()=JSONObject(recognizer.finalResult).optString("text")
    override fun close()=recognizer.close()
}
