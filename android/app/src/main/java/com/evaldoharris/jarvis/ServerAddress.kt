package com.evaldoharris.jarvis

import java.net.URI

object ServerAddress {
    fun normalize(raw: String): String {
        val uri = URI(raw.trim().trimEnd('/'))
        require(uri.scheme in listOf("http", "https") && !uri.host.isNullOrBlank()) { "Informe http://IP:8000 ou um endereço HTTPS." }
        require(uri.userInfo == null && uri.query == null && uri.fragment == null && uri.path.orEmpty() in listOf("", "/")) { "Use apenas o endereço do PC, sem chave, login ou caminho." }
        if (uri.scheme == "http") {
            val parts = uri.host.split('.').mapNotNull { it.toIntOrNull() }
            val privateIp = parts.size == 4 && parts.all { it in 0..255 } &&
                (parts[0] == 10 || parts[0] == 192 && parts[1] == 168 || parts[0] == 172 && parts[1] in 16..31 || parts[0] == 100 && parts[1] in 64..127)
            require(privateIp || uri.host == "localhost" || uri.host == "127.0.0.1" || uri.host.endsWith(".ts.net")) { "Fora da rede local, use uma VPN privada (ex.: Tailscale) ou HTTPS válido." }
        }
        return "${uri.scheme}://${uri.rawAuthority}"
    }
}
