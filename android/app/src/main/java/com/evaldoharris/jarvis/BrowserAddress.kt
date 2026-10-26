package com.evaldoharris.jarvis

import java.net.URI
import java.net.URLEncoder

object BrowserAddress {
    fun normalize(value: String): String {
        val input = value.trim()
        require(input.isNotEmpty() && input.length <= 8192) { "Informe um endereço web válido." }
        val url = if (input.contains(Regex("^[a-zA-Z][a-zA-Z0-9+.-]*:"))) input else "https://$input"
        val parsed = URI(url)
        require(parsed.scheme.lowercase() in listOf("https", "http") && !parsed.host.isNullOrBlank() && parsed.rawUserInfo == null) {
            "Somente páginas HTTP/HTTPS sem credenciais no endereço são permitidas."
        }
        return parsed.toASCIIString()
    }
    fun search(query: String): String {
        require(query.isNotBlank() && query.length <= 2000) { "Informe o que pesquisar." }
        return "https://www.google.com/search?q=" + URLEncoder.encode(query, "UTF-8")
    }
}
