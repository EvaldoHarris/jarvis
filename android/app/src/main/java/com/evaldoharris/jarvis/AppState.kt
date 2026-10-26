package com.evaldoharris.jarvis

import android.os.Handler
import android.os.Looper
import java.util.concurrent.CopyOnWriteArraySet

object AppState {
    private val handler = Handler(Looper.getMainLooper())
    val listeners = CopyOnWriteArraySet<() -> Unit>()
    val messages = mutableListOf<String>()
    @Volatile var connection = "PC desconectado"
    @Volatile var phase = "PRONTO"
    @Volatile var pcReady = false
    @Volatile var stopRemoteSpeech: (() -> Unit)? = null
    @Volatile var expectedPhoneReply = ""
    @Volatile var audioBusy = false
    @Volatile var assistantBusy = false
    @Volatile var manualListening = false
    @Volatile var wakeRunning = false
    @Volatile var mainVisible = false
    @Volatile var wakeReadyUntil = 0L
    fun readyForCommand() = wakeRunning && wakeReadyUntil > System.currentTimeMillis() && !assistantBusy && !audioBusy && !manualListening && expectedPhoneReply.isEmpty()
    @Volatile var lastAudioEnd = 0L
    @Volatile var phoneReplyDeadline = 0L
    @Volatile var assistant: JarvisAssistant? = null
    fun update() { handler.post { listeners.forEach { it() } } }
    fun message(who: String, text: String) {
        synchronized(messages) {
            messages.add("$who: $text")
            while (messages.size > 80) messages.removeAt(0)
        }
        update()
    }
    fun transcript(): String = synchronized(messages) { messages.joinToString("\n\n") }
}
