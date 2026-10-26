package com.evaldoharris.jarvis

import org.junit.Assert.*
import org.junit.Test

class WakePhraseTest {
    @Test fun partialWakeAcknowledgesOnceAndDoesNotConsumeTheFollowingCommand() {
        val wake=WakePhrase()
        assertTrue(wake.preview("Jarvis","wake",1000))
        assertFalse(wake.preview("Jarvis","wake",1100))
        assertTrue(wake.armed(1200))
        assertNull(wake.command("Jarvis","wake",1400))
        assertEquals("que horas são",wake.command("que horas são","wake",2000))
        assertFalse(wake.armed(2100))
    }
    @Test fun partialFullSentenceIsExecutedOnceWithoutRepeatingWakeWord() {
        val wake=WakePhrase()
        assertTrue(wake.preview("Jarvis, abra","wake",1000))
        assertFalse(wake.preview("Jarvis, abra o navegador","wake",1100))
        assertEquals("abra o navegador",wake.command("Jarvis, abra o navegador","wake",1500))
        assertFalse(wake.armed(1600))
        assertNull(wake.command("outra frase","wake",1700))
    }
    @Test fun correctedPartialTimeoutAndRepeatedWakeDoNotBecomeCommands() {
        val wake=WakePhrase()
        assertTrue(wake.preview("Jarvis","wake",1000))
        assertNull(wake.command("carros","wake",1200));assertFalse(wake.armed(1300))
        assertNull(wake.command("Jarvis","wake",2000))
        assertNull(wake.command("Jarvis","wake",3000))
        assertNull(wake.command("fora do prazo","wake",14000))
        assertFalse(wake.preview("Jarvis","continuous",15000))
        assertFalse(wake.preview("Jarvis","off",15000))
    }
    @Test fun onlyWakeWordOrArmedFollowupCanStartRequest() {
        val wake = WakePhrase()
        assertNull(wake.command("abra o navegador", "wake", 1000))
        assertEquals("abra o navegador", wake.command("Jarvis, abra o navegador", "wake", 1000))
        assertNull(wake.command("Jarvis", "wake", 2000))
        assertEquals("que horas são", wake.command("que horas são", "wake", 3000))
        assertNull(wake.command("mais uma conversa", "wake", 4000))
        assertNull(wake.command("Jarvis", "wake", 5000))
        assertNull(wake.command("fora do prazo", "wake", 20000))
    }
    @Test fun continuousAndOffModesRespectSelection() {
        val wake = WakePhrase()
        assertEquals("Olá", wake.command("Olá", "continuous", 1))
        assertNull(wake.command("Jarvis faça algo", "off", 1))
        assertNull(wake.command("palavrajarviscolada", "wake", 1))
    }
    @Test fun armedBySpotterStripsMisheardWakeWordFromCommand() {
        val wake = WakePhrase()
        wake.arm(1000)
        assertEquals("que horas são", wake.command("Chaves, que horas são", "wake", 1500))
        wake.arm(2000)
        assertNull(wake.command("Jarbas", "wake", 2100)); assertTrue(wake.armed(2200))
        assertEquals("abra o TikTok", wake.command("abra o TikTok", "wake", 2300))
        assertEquals("abra o TikTok", WakeWords.stripLeading("Ei, chaves, abra o TikTok"))    }
}
