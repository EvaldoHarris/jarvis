package com.evaldoharris.jarvis

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.Inet4Address
import java.net.InetAddress

/** Liga o PC pela rede (Wake-on-LAN). Só funciona com o celular na mesma rede do PC. */
object PcPower {
    private val MAC = Regex("([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}")
    fun validMac(mac: String) = MAC.matches(mac.trim()) && mac.filter { it.isLetterOrDigit() } != "000000000000"

    fun execute(context: Context, action: String, args: JSONObject): JSONObject {
        if (action != "wake") return PhoneTools.result(false, "Use action=wake.")
        val store = SecureStore(context)
        val macs = store.get("pc_macs").split(",").filter { validMac(it) }
        if (macs.isEmpty()) return PhoneTools.result(false,
            "Ainda não sei o endereço da placa de rede do PC. Conecte o celular ao Jarvis do PC uma vez, com ele ligado, e tente de novo.")
        val targets = broadcasts(context)
        if (targets.isEmpty()) return PhoneTools.result(false,
            "O celular não está em uma rede Wi-Fi. Para ligar o PC, conecte-se ao Wi-Fi de casa.")
        DatagramSocket().use { socket ->
            socket.broadcast = true
            for (mac in macs) {
                val packet = magicPacket(mac)
                // Três envios, em duas portas comuns: um pacote UDP pode se perder.
                repeat(3) { for (to in targets) for (port in intArrayOf(9, 7)) socket.send(DatagramPacket(packet, packet.size, to, port)) }
            }
        }
        return PhoneTools.result(true).put("sent", true).put("pc_on", false)
            .put("message", "Sinal para ligar enviado. O PC costuma levar de 30 segundos a 2 minutos; não dá para confirmar daqui se ele ligou. Se o celular não estiver na rede de casa, o sinal não chega.")
    }

    private fun magicPacket(mac: String): ByteArray {
        val bytes = mac.split(':', '-').map { it.toInt(16).toByte() }
        return ByteArray(6) { 0xFF.toByte() } + List(16) { bytes }.flatten().toByteArray()
    }

    /** Endereços de broadcast do Wi-Fi atual: o geral e o da sub-rede. */
    private fun broadcasts(context: Context): List<InetAddress> {
        val cm = context.getSystemService(ConnectivityManager::class.java)
        val network = cm.allNetworks.firstOrNull {
            cm.getNetworkCapabilities(it)?.let { c -> c.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) || c.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) } == true
        } ?: return emptyList()
        val out = mutableListOf<InetAddress>(InetAddress.getByName("255.255.255.255"))
        cm.getLinkProperties(network)?.linkAddresses?.forEach { link ->
            val ip = link.address as? Inet4Address ?: return@forEach
            val prefix = link.prefixLength
            if (prefix !in 8..30) return@forEach
            val value = ip.address.fold(0) { acc, b -> (acc shl 8) or (b.toInt() and 0xFF) }
            val bcast = value or ((1 shl (32 - prefix)) - 1)
            out += InetAddress.getByAddress(byteArrayOf((bcast ushr 24).toByte(), (bcast ushr 16).toByte(), (bcast ushr 8).toByte(), bcast.toByte()))
        }
        return out
    }
}
