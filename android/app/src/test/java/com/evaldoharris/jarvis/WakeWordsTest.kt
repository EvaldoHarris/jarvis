package com.evaldoharris.jarvis

import org.junit.Assert.*
import org.junit.Test

class WakeWordsTest {
    @Test fun recognizesClosePronunciationsAndKeepsOriginalCommandOffsets(){
        for(word in listOf("Jarvis","Járvis","Jarves","Jervis","Javis","Javes","Djarvis","Jar-vis","Jar vis")){
            val wake=WakePhrase()
            assertEquals(word,"abra o WhatsApp",wake.command("$word, abra o WhatsApp","wake",1000))
        }
        val wake=WakePhrase()
        assertEquals("abra o navegador",wake.command("Ola\u0301, Járvis, abra o navegador","wake",1000))
    }
    @Test fun ordinaryWordsDifferentNamesAndMentioningJarvisDoNotWake(){
        for(text in listOf("já vi","Já vi esse filme","Java","Chaves","Javier","Jardim","Garras","Davis","Travis","avisar","serviço","palavrajarviscolada","O nome do Jarvis é bonito","quero falar sobre Jarvis")){
            val wake=WakePhrase()
            assertNull(text,wake.command(text,"wake",1000));assertFalse(text,wake.armed(1001))
        }
    }
    @Test fun aliasesAreExplicitAndOnlyAtStartOfAddressedSentence(){
        val wake=WakePhrase()
        assertNull(wake.command("Jarbes","wake",1000))
        wake.configureAlias(WakeWords.validateAlias("Jarbes"))
        assertEquals("que horas são",wake.command("Oi, Jarbes, que horas são","wake",2000))
        for(alias in listOf("já vi","Chaves","Jarbas","Java","","uma palavra"))assertThrows(IllegalArgumentException::class.java){WakeWords.validateAlias(alias)}
    }
    @Test fun repeatingWakeWordStillArmsOrExecutesOnlyTheActualRequest(){
        val wake=WakePhrase()
        assertNull(wake.command("Jarvis, Jarvis!","wake",1000));assertTrue(wake.armed(1200))
        assertEquals("que horas são",wake.command("Jarves, Jarvis, que horas são","wake",1500))
    }
    @Test fun alternativesRequireProviderConfidenceAndPreferOriginalWake(){
        assertEquals("xarves",WakeWords.choose(listOf("xarves","Jarvis"),null))
        assertEquals("xarves",WakeWords.choose(listOf("xarves","Jarvis"),floatArrayOf(.9f,.3f)))
        assertEquals("xarves",WakeWords.choose(listOf("xarves","Jarvis"),floatArrayOf(.85f,.8f)))
        assertEquals("Jarvis abre",WakeWords.choose(listOf("carvão abre","Jarvis abre"),null))
        assertEquals("Jarvis abre",WakeWords.choose(listOf("carvão abre","Jarvis abre"),floatArrayOf(.7f,.55f)))
        assertEquals("já vi",WakeWords.choose(listOf("já vi","Jarvis"),floatArrayOf(.85f,.8f)))
        assertEquals("Ei, Chaves",WakeWords.choose(listOf("Ei, Chaves","Ei, Jarvis"),floatArrayOf(.85f,.8f)))
        assertEquals("Javes abra o navegador",WakeWords.choose(listOf("Javes abra o navegador","Jarvis apague tudo"),floatArrayOf(.8f,.9f)))
    }
    @Test fun tolerantSpellingsCommonInPortugueseRecognitionWake(){
        for(word in listOf("Jarbas","Garvis","Xarvis","Jarviz","Jarvi","Harvis","Djavis","Jarvys","Ja vis","Jarvas")){
            assertEquals(word,"abra o TikTok",WakePhrase().command("$word, abra o TikTok","wake",1000))
        }
        assertEquals("que horas são",WakePhrase().command("Ei, oi, Jarvis, que horas são","wake",1000))
        assertEquals("ligue a luz",WakePhrase().command("Bom dia Jarvis ligue a luz","wake",1000))
    }
}
