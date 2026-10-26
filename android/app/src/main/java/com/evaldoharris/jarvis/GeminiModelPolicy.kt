package com.evaldoharris.jarvis

object GeminiModelPolicy {
    fun normalize(raw: String): String {
        val model = raw.trim().removePrefix("models/")
        require(model.matches(Regex("[a-zA-Z0-9._-]+"))) { "Nome de modelo inválido. Use Buscar modelos nas configurações." }
        return model
    }
    fun chatModel(name: String): Boolean = name.startsWith("gemini-") &&
        listOf("embedding", "image", "audio", "tts", "live", "research", "computer-use", "robotics", "video").none { name.contains(it, true) }
    fun fallback(requested: String, available: List<String>, rejected: Set<String>): String? {
        if (!requested.contains("flash", true)) return null
        return available.filter { chatModel(it) && it.contains("flash", true) && it !in rejected &&
            (!requested.contains("lite", true) || it.contains("lite", true)) }
            .sortedWith(compareBy<String> { it.contains("preview") || it.contains("exp") }
                .thenBy { it.contains("lite") }.thenBy { if (it == "gemini-flash-latest") 0 else 1 }.thenByDescending { it })
            .firstOrNull()
    }
    fun error(code: Int, model: String, detail: String): String {
        val summary = when (code) {
            404 -> "Modelo $model não encontrado ou indisponível nessa API. Use Buscar modelos nas configurações."
            429 -> "Limite de uso ou frequência atingido para $model. Confira a cota desse modelo e projeto."
            503 -> "O modelo $model está temporariamente sobrecarregado no Google, mesmo que você tenha cota. Tente novamente em instantes ou escolha outro modelo disponível."
            401, 403 -> "O Google recusou a chave ou o acesso ao modelo $model. Confira as permissões da chave."
            400 -> "O Google recusou os parâmetros enviados ao modelo $model."
            else -> "Falha do provedor ao usar $model (HTTP $code)."
        }
        return "$summary${if (detail.isNotBlank()) " Google: ${detail.take(280)}" else ""}"
    }
}
