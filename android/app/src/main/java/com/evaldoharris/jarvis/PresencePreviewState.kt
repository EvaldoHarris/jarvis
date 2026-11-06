package com.evaldoharris.jarvis

import android.os.Handler
import android.os.Looper
import java.util.concurrent.CopyOnWriteArraySet

/** Short-lived webcam frames in RAM only. */
internal object PresencePreviewState {
    const val NOTICE = "Evaldo, tem uma pessoa não identificada mexendo no seu computador"
    private val handler = Handler(Looper.getMainLooper())
    val listeners = CopyOnWriteArraySet<() -> Unit>()
    @Volatile var alertId = ""
    @Volatile var image: ByteArray? = null
    @Volatile var live = false
    @Volatile var updated = 0L
    fun receive(id: String, bytes: ByteArray, first: Boolean, final: Boolean): Boolean {
        if (!id.matches(Regex("alert_[a-f0-9]{24}")) || bytes.size > 700000) return false
        if (!first && id != alertId) return false
        if (first) alertId = id
        if (bytes.isNotEmpty()) image = bytes
        live = !final; updated = android.os.SystemClock.elapsedRealtime()
        handler.post { listeners.forEach { it() } }
        val expected = alertId
        handler.postDelayed({ if (alertId == expected && android.os.SystemClock.elapsedRealtime() - updated >= 60000) clear() }, 61000)
        return true
    }
    fun clear() { alertId = ""; image = null; live = false; handler.post { listeners.forEach { it() } } }
}
