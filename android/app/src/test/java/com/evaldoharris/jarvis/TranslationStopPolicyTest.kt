package com.evaldoharris.jarvis

import org.junit.Assert.*
import org.junit.Test

class TranslationStopPolicyTest {
    @Test fun acceptsOnlyConfidentWakeAndStop() {
        assertTrue(TranslationStopPolicy.accepts("Jarvis, pare a tradução",.9))
        assertTrue(TranslationStopPolicy.accepts("jarbas desative a tradução",.85))
        assertTrue(TranslationStopPolicy.accepts("chaves pare de traduzir",.85))
        assertFalse(TranslationStopPolicy.accepts("pare a tradução",.99))
        assertFalse(TranslationStopPolicy.accepts("Jarvis abra o banco",.99))
        assertFalse(TranslationStopPolicy.accepts("Jarvis pare a tradução",.4))
    }
    @Test fun ignoresTheNarratorReadingTheSameStopInstruction() {
        assertFalse(TranslationStopPolicy.accepts("jarbas pare a tradução",.95,"Jarvis, pare a tradução",true))
        assertTrue(TranslationStopPolicy.accepts("jarbas pare a tradução",.95,"Hoje veremos como funciona um computador",true))
    }
}
