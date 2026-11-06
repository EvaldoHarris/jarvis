package com.evaldoharris.jarvis

import java.text.Normalizer

/** Pure rules shared by UI, speech commands and bounded worker queues. */
object TranslationPolicy {
    const val MAX_AGE_MS = 5000L
    fun fresh(created: Long, now: Long) = now >= created && now - created <= MAX_AGE_MS
    fun command(text: String): String? {
        val s = Normalizer.normalize(text.lowercase(), Normalizer.Form.NFD).replace(Regex("\\p{M}+"), "")
        if (!(s.contains("traduc") || s.contains("traduz") || s.contains("tradutor") || s.contains("legendas"))) return null
        if (Regex("\\bnao\\b").containsMatchIn(s)) return null
        return when {
            Regex("\\b(parar|pare|encerrar|encerre|desligar|desligue|desativar|desative|desativa|cancelar|cancele|cancela)\\b").containsMatchIn(s) || s.contains("para a traduc") -> "stop"
            s.contains("somente legendas") || s.contains("sem voz") || s.contains("sem audio") -> "audio_off"
            s.contains("ativar audio") || s.contains("ative o audio") || s.contains("ouvir traduc") -> "audio_on"
            s.contains("status") -> "status"
            Regex("\\b(traduza|traduzir|ativar|ative|ativa|iniciar|inicie|inicia|ligar|ligue|liga|comece|comecar)\\b").containsMatchIn(s) &&
                (listOf("video", "assistindo", "tempo real", "legendas", "traducao", "tradutor").any { s.contains(it) }) -> "start"
            else -> null
        }
    }
}
