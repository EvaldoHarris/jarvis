package com.evaldoharris.jarvis

import android.content.Context
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.VibrationEffect
import android.os.Vibrator

/** Immediate local acknowledgement, without a network call or spoken echo. */
internal class WakeCue(context:Context) {
    private val vibrator=context.getSystemService(Vibrator::class.java)
    private var tone:ToneGenerator?=null
    fun play(){
        runCatching{
            if(tone==null)tone=ToneGenerator(AudioManager.STREAM_MUSIC,60)
            tone?.startTone(ToneGenerator.TONE_PROP_BEEP2,100)
        }
        runCatching{if(vibrator?.hasVibrator()==true)vibrator.vibrate(VibrationEffect.createOneShot(40,VibrationEffect.DEFAULT_AMPLITUDE))}
    }
    fun close(){tone?.release();tone=null}
}
