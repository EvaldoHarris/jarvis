package com.evaldoharris.jarvis

import org.junit.Assert.*
import org.junit.Test

class TranslationPcmTest {
    @Test fun boostsQuietSpeechWithoutClipping() {
        val input=floatArrayOf(0.02f,-0.02f,0.03f,-0.03f)
        val output=TranslationPcm.normalized(input)
        assertTrue(output[0]>input[0]);assertTrue(output.all { kotlin.math.abs(it)<=1f })
        assertTrue(output[0]<=input[0]*3.21f)
    }
    @Test fun preservesSilenceAndStrongSignals() {
        assertArrayEquals(FloatArray(12),TranslationPcm.normalized(FloatArray(12)),0f)
        val strong=floatArrayOf(.95f,-.95f)
        assertArrayEquals(strong,TranslationPcm.normalized(strong),.0001f)
    }
    @Test fun handlesInvalidNativeSamples() {
        assertTrue(TranslationPcm.normalized(floatArrayOf(Float.NaN,Float.POSITIVE_INFINITY)).all { it==0f })
    }
}
