package com.evaldoharris.jarvis

import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs
import kotlin.math.sqrt

object TranslationPcm {
    /** Raise quiet speech, bounded by both gain and peak; never clip or amplify silence. */
    fun normalized(samples: FloatArray): FloatArray {
        if (samples.isEmpty()) return samples
        var sum = 0.0; var peak = 0f
        for (sample in samples) { val v=if(sample.isFinite()) sample else 0f;sum+=v.toDouble()*v;peak=maxOf(peak,abs(v)) }
        val rms=sqrt(sum/samples.size)
        val gain=if(rms<0.0001 || peak<0.0001f) 1.0 else minOf(3.2,0.18/rms,0.94/peak).coerceAtLeast(1.0)
        return FloatArray(samples.size) { if(samples[it].isFinite()) (samples[it]*gain).toFloat().coerceIn(-1f,1f) else 0f }
    }
    fun writeWav(samples: FloatArray, rate: Int, output: File) {
        require(rate>0)
        val data=ByteBuffer.allocate(44+samples.size*2).order(ByteOrder.LITTLE_ENDIAN)
        data.put("RIFF".toByteArray(Charsets.US_ASCII)).putInt(36+samples.size*2).put("WAVEfmt ".toByteArray(Charsets.US_ASCII))
        data.putInt(16).putShort(1).putShort(1).putInt(rate).putInt(rate*2).putShort(2).putShort(16)
        data.put("data".toByteArray(Charsets.US_ASCII)).putInt(samples.size*2)
        for(sample in samples)data.putShort((sample.coerceIn(-1f,1f)*32767).toInt().toShort())
        output.writeBytes(data.array())
    }
}
