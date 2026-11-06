package com.evaldoharris.jarvis

import org.junit.Assert.*
import org.junit.Test

class TranslationPacingTest {
    @Test fun backlogSpeedsUpWithinAnIntelligibleLimit() {
        val small=TranslationPacing.speed(1000,1)
        val delayed=TranslationPacing.speed(8000,2)
        val severe=TranslationPacing.speed(20000,8)
        assertTrue(small>1f);assertTrue(delayed>small)
        assertTrue(severe>delayed);assertTrue(severe<=1.45f)
    }
    @Test fun aSinglePhraseDoesNotRushBecauseOfAnAssistantPause() {
        assertEquals(TranslationPacing.speed(100,0),TranslationPacing.speed(60000,0),0f)
    }
}
