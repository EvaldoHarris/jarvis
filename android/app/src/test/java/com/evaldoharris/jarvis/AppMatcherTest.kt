package com.evaldoharris.jarvis

import org.junit.Assert.*
import org.junit.Test

class AppMatcherTest {
    private val apps = listOf(
        "TikTok" to "com.zhiliaoapp.musically", "WhatsApp" to "com.whatsapp", "WhatsApp Business" to "com.whatsapp.w4b",
        "Calendário" to "com.samsung.android.calendar", "Calculadora" to "com.sec.android.app.popupcalculator",
        "YouTube" to "com.google.android.youtube", "YouTube Music" to "com.google.android.apps.youtube.music",
        "Google" to "com.google.android.googlequicksearchbox", "Google Home" to "com.google.android.apps.chromecast.app",
        "Meus Arquivos" to "com.sec.android.app.myfiles", "Relógio" to "com.sec.android.app.clockpackage",
        "Instagram" to "com.instagram.android", "Netflix" to "com.netflix.mediaclient", "Chrome" to "com.android.chrome",
    )
    private fun open(q: String) = AppMatcher.best(q, apps)?.first

    @Test fun findsAppsAsSpeechRecognitionWritesThem() {
        assertEquals("TikTok", open("Tik Tok"))
        assertEquals("TikTok", open("tiktok"))
        assertEquals("Calendário", open("calendario"))
        assertEquals("Relógio", open("relogio"))
        assertEquals("WhatsApp", open("WhatsApp"))
        assertEquals("WhatsApp", open("o app do WhatsApp"))
        assertEquals("YouTube", open("youtube"))
        assertEquals("YouTube Music", open("youtube music"))
        assertEquals("Meus Arquivos", open("meus arquivos"))
        assertEquals("Instagram", open("instagran"))
        assertEquals("Netflix", open("netflix"))
        assertEquals("Calculadora", open("a calculadora"))
        assertEquals("Google", open("google"))
    }
    @Test fun unknownAppsAreNotOpened() {
        assertNull(open("spotify"))
        assertNull(open("ab"))
    }
}
