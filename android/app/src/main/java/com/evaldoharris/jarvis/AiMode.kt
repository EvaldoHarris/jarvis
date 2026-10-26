package com.evaldoharris.jarvis

object AiMode {
    val values = listOf("auto", "gemini", "local")
    fun normalize(value: String) = value.takeIf { it in values } ?: "auto"
    fun fallback(mode: String, transient: Boolean, installed: Boolean, cancelled: Boolean) =
        normalize(mode) == "auto" && transient && installed && !cancelled
}
