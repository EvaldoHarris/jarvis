package com.evaldoharris.jarvis

import java.net.URLEncoder

object CameraAddress {
    fun build(host: String, port: Int, vendor: String, username: String, password: String, channel: Int, stream: Int, channels: Int = 64): String {
        val ip = host.split('.').map { it.toIntOrNull() ?: -1 }
        require(ip.size == 4 && ip.all { it in 0..255 } && (ip[0] == 10 || ip[0] == 192 && ip[1] == 168 || ip[0] == 172 && ip[1] in 16..31 || ip[0] == 100 && ip[1] in 64..127)) { "Use o IP privado da câmera, acessível pela rede local ou VPN." }
        require(port in 1..65535 && channels in 1..64 && channel in 1..channels && stream in 0..1) { "Porta, canal ou stream inválido." }
        require(username.isNotBlank() && password.isNotBlank()) { "Cadastre usuário e senha do dispositivo em CASA → CÂMERAS." }
        fun encode(s: String) = URLEncoder.encode(s, "UTF-8").replace("+", "%20")
        return when (vendor) {
            "intelbras" -> "rtsp://${encode(username)}:${encode(password)}@$host:$port/cam/realmonitor?channel=$channel&subtype=$stream"
            "icsee" -> "rtsp://$host:$port/user=${encode(username)}&password=${encode(password)}&channel=$channel&stream=$stream.sdp"
            else -> error("Tipo de câmera inválido; escolha intelbras ou icsee.")
        }
    }
}
