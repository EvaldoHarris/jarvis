package com.evaldoharris.jarvis

import org.junit.Assert.*
import org.junit.Test

class VoiceInputPolicyTest {
    @Test fun serverDisconnectGetsOnlyOneAutomaticRetry() {
        assertTrue(VoiceInputPolicy.retryDisconnected(11, false))
        assertFalse(VoiceInputPolicy.retryDisconnected(11, true))
        for (error in listOf(1, 2, 3, 5, 7, 8, 9, 12, 13)) assertFalse(VoiceInputPolicy.retryDisconnected(error, false))
    }
    @Test fun permissionsAndLanguageFailuresHaveActionableMessages() {
        assertTrue(VoiceInputPolicy.message(9).contains("Permita o microfone"))
        assertTrue(VoiceInputPolicy.message(11).contains("desconectou"))
        assertTrue(VoiceInputPolicy.message(13).contains("Baixe o idioma"))
    }
}
