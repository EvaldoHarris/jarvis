package com.evaldoharris.jarvis

/** One authenticated PC speech stream; microphone requests keep their own ID. */
internal class PresenceReplyGate {
    private var id = ""
    private var deadline = 0L

    @Synchronized fun start(request: String, enabled: Boolean, ttlMs: Long, now: Long): Boolean {
        if (!enabled || !request.matches(Regex("presence_[a-f0-9]{24}")) || ttlMs !in 1..15000) return false
        id = request; deadline = now + 60000
        return true
    }
    @Synchronized fun accepts(request: String, now: Long): Boolean {
        if (now > deadline) clear()
        return id.isNotEmpty() && request == id
    }
    @Synchronized fun touch(now: Long) { deadline = now + 60000 }
    @Synchronized fun clear() { id = ""; deadline = 0L }
}
