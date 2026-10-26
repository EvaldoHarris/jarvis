package com.evaldoharris.jarvis

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.Build
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.UUID
import java.util.Locale
import java.util.concurrent.Executors

class PhoneControlService : Service() {
    private val handler = Handler(Looper.getMainLooper())
    private val network = Executors.newSingleThreadExecutor()
    private val controls = Executors.newSingleThreadExecutor()
    private lateinit var pc: PcClient
    private var socket: WebSocket? = null
    private var logs: WebSocket? = null
    @Volatile private var stopped = false
    @Volatile private var connecting = false
    private val completed = LinkedHashMap<String, JSONObject>()
    private val heartbeat = object : Runnable {
        override fun run() {
            if (!stopped) { socket?.send("{\"type\":\"ping\"}"); handler.postDelayed(this, 30000) }
        }
    }
    override fun onCreate() {
        super.onCreate(); pc = PcClient(this)
        AppState.stopRemoteSpeech = { AppState.expectedPhoneReply = ""; GeminiVoice.stop() }
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("jarvis_link", "Ligação com o PC", NotificationManager.IMPORTANCE_LOW))
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val stop = PendingIntent.getService(this, 1, Intent(this, javaClass).setAction("stop"), PendingIntent.FLAG_IMMUTABLE)
        startForeground(1, Notification.Builder(this, "jarvis_link").setSmallIcon(R.drawable.ic_reactor)
            .setContentTitle("JARVIS — controle entre aparelhos")
            .setContentText("Conexão com o PC e respostas no celular. Desconectar encerra a ligação.")
            .setContentIntent(open).setOngoing(true).addAction(Notification.Action.Builder(null, "Desconectar", stop).build()).build())
        handler.postDelayed(heartbeat, 30000)
    }
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "stop") { pc.store.put("remote_enabled", "false"); pc.store.put("phone_reply_enabled", "false"); stopSelf(); return START_NOT_STICKY }
        if (intent?.action == "listen_reply") pc.store.put("phone_reply_enabled", "true")
        if (pc.store.get("remote_enabled") != "true" && pc.store.get("phone_reply_enabled") != "true") { stopSelf(); return START_NOT_STICKY }
        connect(); return START_STICKY
    }
    private fun connect() {
        if (stopped || connecting || socket != null) return
        connecting = true
        network.execute {
            try {
                val token = pc.renew()
                val url = pc.address().replaceFirst("http", "ws")
                val request = Request.Builder().url("$url/ws/android").header("Authorization", "Bearer $token").build()
                val pending = pc.client.newWebSocket(request, object : WebSocketListener() {
                    override fun onOpen(webSocket: WebSocket, response: Response) {
                        var id = pc.store.get("device_id")
                        if (id.isEmpty()) { id = UUID.randomUUID().toString(); pc.store.put("device_id", id) }
                        webSocket.send(JSONObject().put("type", "hello").put("device_id", id).put("name", "${Build.MANUFACTURER} ${Build.MODEL}").toString())
                    }
                    override fun onMessage(webSocket: WebSocket, text: String) {
                        try {
                            val message = JSONObject(text)
                            if (message.optString("type") in listOf("ready", "pong")) {
                                message.optString("voice_name").takeIf { it.isNotBlank() }?.let { pc.store.put("voice_name", it) }
                                message.optString("voice_model").takeIf { it.isNotBlank() }?.let { pc.store.put("voice_model", it) }
                            }
                            if (message.optString("type") == "ready") {
                                AppState.pcReady = true
                                AppState.connection = if (pc.store.get("remote_enabled") == "true") "PC conectado • controle ativo" else "PC conectado • respostas no celular"
                                AppState.update()
                            }
                            if (message.optString("type") == "assistant_reply") {
                                val answer = message.optString("text")
                                if (answer.isNotBlank()) AppState.message("JARVIS / PC", answer)
                                if (message.optString("request_id") == AppState.expectedPhoneReply) {
                                    val finalReply = message.optBoolean("final_reply", true)
                                    if (finalReply) AppState.expectedPhoneReply = ""
                                    if (message.optBoolean("audio_streamed") && finalReply) GeminiVoice.finishPc(message.optString("request_id"))
                                    else if (message.optBoolean("audio_streamed")) { /* audio continues after tool result */ }
                                    else handler.post { GeminiVoice.speak(applicationContext, answer) }
                                }
                            }
                            if (message.optString("type") == "assistant_audio" && message.optString("request_id") == AppState.expectedPhoneReply && pc.store.get("speak", "true") == "true") {
                                AppState.phoneReplyDeadline = System.currentTimeMillis() + 60000
                                GeminiVoice.pcAudio(message.getString("request_id"), android.util.Base64.decode(message.getString("data"), android.util.Base64.NO_WRAP), message.optInt("rate", 24000))
                            }
                            if (message.optString("type") == "command") controls.execute {
                                val id = message.optString("id")
                                if (id.isEmpty() || stopped) return@execute
                                val result = completed[id] ?: if (message.optDouble("expires_at", 0.0) * 1000 < System.currentTimeMillis())
                                    PhoneTools.result(false, "Comando expirado; não executado.")
                                else if (pc.store.get("remote_enabled") != "true") PhoneTools.result(false, "Controle remoto desativado.")
                                else PhoneTools.execute(this@PhoneControlService, message.optString("action"), message.optJSONObject("args") ?: JSONObject())
                                completed[id] = result
                                while (completed.size > 32) completed.remove(completed.keys.first())
                                webSocket.send(JSONObject().put("type", "result").put("id", id).put("result", result).toString())
                            }
                        } catch (_: Exception) { AppState.message("SYS", "Comando remoto inválido; não executado.") }
                    }
                    override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) = reconnect(webSocket)
                    override fun onClosed(webSocket: WebSocket, code: Int, reason: String) = reconnect(webSocket)
                    override fun onClosing(webSocket: WebSocket, code: Int, reason: String) { webSocket.close(code, null) }
                })
                if (stopped) pending.cancel() else socket = pending
                logs?.cancel()
                logs = pc.client.newWebSocket(Request.Builder().url("$url/ws?token=$token").build(), object : WebSocketListener() {
                    override fun onMessage(webSocket: WebSocket, text: String) {
                        try {
                            val data = JSONObject(text)
                            if (data.optString("type") == "log") AppState.message("PC / " + data.optString("speaker"), data.optString("text"))
                        } catch (_: Exception) { }
                    }
                })
            } catch (_: PcClient.Unauthorized) {
                AppState.connection = "Pareamento recusado; conecte novamente ao PC"; AppState.update()
                pc.store.put("remote_enabled", "false"); handler.post { stopSelf() }
            } catch (_: Exception) {
                AppState.connection = "PC offline • Android independente"; AppState.update()
                handler.postDelayed({ connect() }, 4000)
            } finally { connecting = false }
        }
    }
    private fun reconnect(webSocket: WebSocket) {
        AppState.pcReady = false
        if (socket === webSocket) socket = null
        AppState.connection = "PC offline • Android independente"; AppState.update()
        handler.postDelayed({ connect() }, 3000)
    }
    override fun onDestroy() {
        stopped = true; handler.removeCallbacksAndMessages(null)
        AppState.pcReady = false
        pc.store.put("phone_reply_enabled", "false")
        AppState.stopRemoteSpeech = null
        socket?.cancel(); logs?.cancel(); network.shutdownNow(); controls.shutdownNow()
        AppState.connection = "PC desconectado"; AppState.update(); super.onDestroy()
    }
    override fun onBind(intent: Intent?): IBinder? = null
}
