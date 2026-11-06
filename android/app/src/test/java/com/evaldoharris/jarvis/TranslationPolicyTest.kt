package com.evaldoharris.jarvis

import org.junit.Assert.*
import org.junit.Test

class TranslationPolicyTest {
    @Test fun routesVideoCommandsWithoutAnAiCall() {
        assertEquals("start", TranslationPolicy.command("Traduza o vídeo que estou assistindo com voz"))
        assertEquals("start", TranslationPolicy.command("Jarvis, ative a tradução"))
        assertEquals("start", TranslationPolicy.command("Jarvis liga o tradutor"))
        assertEquals("start", TranslationPolicy.command("Inicia a tradução com voz"))
        assertEquals("stop", TranslationPolicy.command("Pare a tradução"))
        assertEquals("audio_off", TranslationPolicy.command("Somente legendas"))
        assertEquals("audio_on", TranslationPolicy.command("Ative o áudio da tradução"))
        assertEquals("status", TranslationPolicy.command("Status da tradução"))
    }
    @Test fun doesNotStealTextTranslationRequestsOrNegations() {
        assertNull(TranslationPolicy.command("Traduza este texto para português: hello"))
        assertNull(TranslationPolicy.command("Não traduza o vídeo"))
        assertNull(TranslationPolicy.command("O que você consegue traduzir?"))
    }
    @Test fun dropsStaleAndInvalidClockItems() {
        assertTrue(TranslationPolicy.fresh(1000, 1200))
        assertFalse(TranslationPolicy.fresh(1000, 7000))
        assertFalse(TranslationPolicy.fresh(2000, 1000))
    }
}
