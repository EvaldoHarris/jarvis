package com.evaldoharris.jarvis

import java.text.Normalizer

internal object TranslationStopPolicy {
    val prefixes=listOf("jarbas","chaves","harvey","já vis","jarvis")
    val requests=listOf("pare a tradução","parar a tradução","para a tradução","pare de traduzir","parar de traduzir",
        "desative a tradução","desativar a tradução","cancele a tradução","desligue o tradutor","pare o tradutor")
    fun grammar()=prefixes.flatMap { prefix->requests.map { "$prefix $it" } }+"[unk]"
    fun normalized(value:String):String=Normalizer.normalize(value.lowercase(java.util.Locale.ROOT),Normalizer.Form.NFD)
        .replace(Regex("\\p{M}+"),"").replace(Regex("[^a-z ]")," ").trim().replace(Regex(" +")," ")
    fun canonical(value:String):String {
        val text=normalized(value)
        val prefix=prefixes.map(::normalized).firstOrNull { text==it||text.startsWith("$it ") }
        return if(prefix!=null)"jarvis"+text.removePrefix(prefix) else text
    }
    fun accepts(text:String,confidence:Double,spokenText:String="",speaking:Boolean=false):Boolean {
        val clean=canonical(text)
        if(confidence<0.70||!clean.startsWith("jarvis ")||TranslationPolicy.command(clean)!="stop")return false
        // Never treat a translated sentence explicitly reading this command as its user.
        if(speaking&&canonical(spokenText).contains(clean))return false
        return true
    }
}
