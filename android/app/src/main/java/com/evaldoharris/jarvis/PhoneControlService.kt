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
    private val presenceReplies = PresenceReplyGate()
    private lateinit var presenceAudio: PresencePhoneAudio
    private val heartbeat = object : Runnable {
        override fun run() {
            if (!stopped) { socket?.send("{\"type\":\"ping\"}"); handler.postDelayed(this, 30000) }
        }
    }
    override fun onCreate() {
        super.onCreate(); pc = PcClient(this)
        presenceAudio = PresencePhoneAudio(applicationContext)
        AppState.stopRemoteSpeech = { AppState.expectedPhoneReply = ""; presenceReplies.clear(); presenceAudio.stop(); GeminiVoice.stop() }
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
                        webSocket.send(JSONObject().put("type", "hello").put("device_id", id).put("name", "${Build.MANUFACTURER} ${Build.MODEL}").put("presence_audio", true).put("presence_video", true).toString())
                    }
                    override fun onMessage(webSocket: WebSocket, text: String) {
                        try {
                            val message = JSONObject(text)
                            val requestId = message.optString("request_id")
                            if (message.optString("type") in listOf("presence_alert", "presence_frame")) {
                                val first = message.optString("type") == "presence_alert"
                                val encoded = message.optString("image")
                                if (encoded.length <= 950000 && PresencePreviewState.receive(message.optString("alert_id"),
                                        android.util.Base64.decode(encoded, android.util.Base64.NO_WRAP), first, message.optBoolean("final"))) {
                                    if (first) {
                                        AppState.message("JARVIS", PresencePreviewState.NOTICE)
                                        handler.post { PresenceAlertActivity.notify(applicationContext) }
                                        if (pc.store.get("speak", "true") == "true") presenceAudio.warning()
                                    }
                                }
                            }
                            if (message.optString("type") == "assistant_start") {
                                val enabled = pc.store.get("speak", "true") == "true" &&
                                    (pc.store.get("phone_reply_enabled") == "true" || pc.store.get("remote_enabled") == "true")
                                val accepted = presenceReplies.start(requestId,
                                    enabled, message.optLong("ttl_ms", 5000), android.os.SystemClock.elapsedRealtime())
                                webSocket.send(JSONObject().put("type", "result").put("id", requestId)
                                    .put("result", JSONObject().put("ok", accepted).put("error", if (!enabled) "phone_voice_disabled" else if (!accepted) "invalid_speech_request" else "")).toString())
                            }
                            if (message.optString("type") == "assistant_cancel" && presenceReplies.accepts(requestId, android.os.SystemClock.elapsedRealtime())) {
                                presenceReplies.clear(); presenceAudio.stop()
                            }
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
                                val routed = presenceReplies.accepts(requestId, android.os.SystemClock.elapsedRealtime())
                                if (requestId == AppState.expectedPhoneReply || routed) {
                                    val finalReply = message.optBoolean("final_reply", true)
                                    if (finalReply && requestId == AppState.expectedPhoneReply) AppState.expectedPhoneReply = ""
                                    if (finalReply && routed) presenceReplies.clear()
                                    if (!message.optBoolean("speak", true)) { /* Transcript only: webcam selected another output. */ }
                                    else if (message.optBoolean("audio_streamed") && finalReply && routed) presenceAudio.finish(requestId)
                                    else if (message.optBoolean("audio_streamed") && finalReply) GeminiVoice.finishPc(requestId)
                                    else if (message.optBoolean("audio_streamed")) { /* audio continues after tool result */ }
                                    else if (routed) presenceAudio.text(answer)
                                    else handler.post { GeminiVoice.speak(applicationContext, answer) }
                                }
                            }
                            if (message.optString("type") == "assistant_audio" &&
                                (requestId == AppState.expectedPhoneReply || presenceReplies.accepts(requestId, android.os.SystemClock.elapsedRealtime())) && pc.store.get("speak", "true") == "true") {
                                val routed = presenceReplies.accepts(requestId, android.os.SystemClock.elapsedRealtime())
                                presenceReplies.touch(android.os.SystemClock.elapsedRealtime())
                                AppState.phoneReplyDeadline = System.currentTimeMillis() + 60000
                                val pcm = android.util.Base64.decode(message.getString("data"), android.util.Base64.NO_WRAP)
                                if (routed) presenceAudio.audio(requestId, pcm, message.optInt("rate", 24000))
                                else GeminiVoice.pcAudio(requestId, pcm, message.optInt("rate", 24000))
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
        presenceReplies.clear(); GeminiVoice.stop()
        presenceAudio.close(); PresencePreviewState.clear()
        AppState.pcReady = false
        pc.store.put("phone_reply_enabled", "false")
        AppState.stopRemoteSpeech = null
        socket?.cancel(); logs?.cancel(); network.shutdownNow(); controls.shutdownNow()
        AppState.connection = "PC desconectado"; AppState.update(); super.onDestroy()
    }
    override fun onBind(intent: Intent?): IBinder? = null
}
