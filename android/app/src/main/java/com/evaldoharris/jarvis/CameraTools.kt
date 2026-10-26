package com.evaldoharris.jarvis

import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit

object CameraTools {
    @Volatile internal var current: CameraActivity? = null
    fun list(context: Context): JSONArray = PersonalData.read(context, "home_cameras")
    fun selected(context: Context, name: String): JSONObject {
        val entries = list(context)
        val matches = (0 until entries.length()).map { entries.getJSONObject(it) }.filter {
            it.getString("id") == name || it.getString("name").equals(name, true) || it.optString("vendor").equals(name, true)
        }
        require(matches.size == 1) { "Câmera ausente ou ambígua; use camera list para escolher o nome ou ID." }
        return matches.single()
    }
    fun url(camera: JSONObject, channel: Int) = CameraAddress.build(camera.getString("host"), camera.optInt("port", 554), camera.getString("vendor"),
        camera.optString("username"), camera.optString("password"), channel, camera.optInt("stream", 1), camera.optInt("channel_count", 64))
    fun execute(context: Context, action: String, args: JSONObject): JSONObject {
        if (action == "list") return PhoneTools.result(true).put("cameras", JSONArray().apply {
            val items = list(context)
            for (i in 0 until items.length()) items.getJSONObject(i).let { put(JSONObject().put("id", it.getString("id")).put("name", it.getString("name")).put("vendor", it.getString("vendor")).put("channels", it.optInt("channel_count", 64))) }
        })
        val future = CompletableFuture<JSONObject>()
        val handler = Handler(Looper.getMainLooper())
        if (action == "stop") { handler.post { current?.finish(); future.complete(PhoneTools.result(true)) }; return future.get(5, TimeUnit.SECONDS) }
        if (action == "snapshot") {
            handler.post {
                try {
                    val live = current ?: error("Abra uma câmera antes de pedir uma imagem.")
                    future.complete(live.snapshot())
                } catch (e: Exception) { future.complete(PhoneTools.result(false, e.message ?: "Imagem indisponível.")) }
            }
            return future.get(5, TimeUnit.SECONDS)
        }
        require(action == "open") { "Ação de câmera desconhecida." }
        val camera = selected(context, args.optString("name"))
        val channel = args.optInt("channel", camera.optInt("channel", 1))
        url(camera, channel) // Validate before disturbing another active camera.
        handler.post {
            try {
                context.startActivity(Intent(context, CameraActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                    .putExtra("camera_id", camera.getString("id")).putExtra("channel", channel))
                future.complete(PhoneTools.result(true).put("opened", true).put("playing", false).put("note", "Player aberto; aguardando imagem da câmera."))
            } catch (_: Exception) { future.complete(PhoneTools.result(false, "Android não permitiu abrir o player. Abra CASA no aplicativo.")) }
        }
        val opened = future.get(5, TimeUnit.SECONDS)
        if (!opened.optBoolean("ok")) return opened
        val deadline = System.currentTimeMillis() + 12000
        while (System.currentTimeMillis() < deadline) {
            val live = current
            if (live?.cameraId == camera.getString("id") && live.channel == channel) {
                if (live.error.isNotEmpty()) return PhoneTools.result(false, live.error)
                if (live.freshFrame()) return PhoneTools.result(true).put("playing", true).put("name", camera.getString("name")).put("channel", channel)
            }
            Thread.sleep(100)
        }
        return PhoneTools.result(false, "A câmera não entregou imagem em 12 segundos. Confira rede/VPN, credenciais, canal e vídeo H.264; outras câmeras continuam independentes.")
    }
}
