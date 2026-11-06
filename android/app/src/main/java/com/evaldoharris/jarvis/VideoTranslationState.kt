package com.evaldoharris.jarvis

object VideoTranslationState {
    @Volatile var active = false
    @Volatile var status = "Tradução parada"
    @Volatile var caption = ""
    @Volatile var audio = true
    @Volatile var pauseNarrationUntil=0L
    @Volatile var speaking=false
    @Volatile var spokenText=""
    @Volatile var lastNarrationEnd=0L
    fun update(message: String) { status = message; AppState.update() }
}
