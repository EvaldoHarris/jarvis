package com.evaldoharris.jarvis

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Base64
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * Sessão Live contínua com o Gemini, a mesma tecnologia usada pelo PC.
 * A conexão fica aberta entre pedidos: o Gemini chama as ferramentas do celular e responde em áudio
 * enquanto ainda está gerando, sem reenviar o histórico a cada etapa.
 */
internal class LiveSession(
    private val context: Context,
    private val tools: () -> JSONArray,
    private val instruction: () -> String,
    private val runTool: (String, JSONObject) -> JSONObject,
) {
    /** Resultado de um pedido. `toolsRan` indica se alguma ação já foi executada (então não é seguro repetir). */
    class Outcome(val answer: String?, val error: String?, val toolsRan: Boolean)

    private class Turn(val done: (Outcome) -> Unit) {
        val text = StringBuilder()
        var toolsRan = false
        var finished = false
        var started = android.os.SystemClock.elapsedRealtime()
        var firstAudio = false
        @Volatile var lastServer = 0L
    }

    companion object {
        private val client = OkHttpClient.Builder().connectTimeout(8, TimeUnit.SECONDS).readTimeout(0, TimeUnit.MILLISECONDS)
            .pingInterval(15, TimeUnit.SECONDS).build()
        private const val URL = "https://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
        private const val IDLE_CLOSE_MS = 8 * 60_000L
        private const val TURN_TIMEOUT_MS = 180_000L
    }

    private val store = SecureStore(context)
    private val toolWorker = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private val lock = Any()
    private var socket: WebSocket? = null
    private var ready = false
    private var expiring = false
    private var identity = ""
    private var resumeHandle = ""
    private var pending: String? = null
    private var turn: Turn? = null
    private var session = 0
    private val idleClose = Runnable { synchronized(lock) { if (turn == null) closeLocked() } }

    /** Abre a conexão antes do pedido (por exemplo, quando a palavra Jarvis é ouvida). */
    fun warm() { synchronized(lock) { runCatching { ensureLocked() } } }

    fun ask(text: String, image: String?, done: (Outcome) -> Unit) {
        synchronized(lock) {
            if (turn != null) { done(Outcome(null, "Já há um pedido em andamento.", false)); return }
            val current = Turn(done)
            turn = current
            try { ensureLocked() } catch (e: Exception) { turn = null; done(Outcome(null, e.message ?: "Live indisponível.", false)); return }
            val parts = JSONArray().put(JSONObject().put("text", text))
            if (image != null) parts.put(JSONObject().put("inlineData", JSONObject().put("mimeType", "image/jpeg").put("data", image)))
            val message = JSONObject().put("clientContent", JSONObject()
                .put("turns", JSONArray().put(JSONObject().put("role", "user").put("parts", parts)))
                .put("turnComplete", true)).toString()
            if (ready) socket?.send(message) else pending = message
            main.removeCallbacks(idleClose)
            val id = session
            main.postDelayed({ synchronized(lock) {
                if (turn === current && session == id) finishLocked(Outcome(null, "O Gemini Live demorou demais para responder.", current.toolsRan), close = true)
            } }, TURN_TIMEOUT_MS)
        }
    }

    fun cancel() {
        synchronized(lock) {
            turn?.let { finishLocked(Outcome(null, "Pedido interrompido.", it.toolsRan), close = true) }
            resumeHandle = ""
        }
    }

    private fun currentIdentity(): Triple<String, String, String> {
        val key = store.get("gemini_key")
        require(key.isNotBlank()) { "Cadastre sua chave Gemini nas configurações." }
        val voice = store.get("voice_name", "Charon")
        val model = GeminiModelPolicy.normalize(store.get("voice_model", "models/gemini-3.1-flash-live-preview"))
        return Triple(key, voice, model)
    }

    private fun ensureLocked() {
        val (key, voice, model) = currentIdentity()
        val id = listOf(key, voice, model).joinToString("\u0000")
        if (socket != null && identity == id && !expiring) return
        closeLocked()
        if (identity != id) resumeHandle = ""
        identity = id; ready = false; expiring = false
        val mySession = ++session
        val url = URL.toHttpUrl().newBuilder().addQueryParameter("key", key).build().toString().replaceFirst("https", "wss")
        val setup = setup(voice, model)
        socket = client.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) { ws.send(setup) }
            override fun onMessage(ws: WebSocket, text: String) { handle(mySession, ws, text) }
            override fun onMessage(ws: WebSocket, bytes: ByteString) { handle(mySession, ws, bytes.utf8()) }
            override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                android.util.Log.w("JarvisLive", "failure ${response?.code} ${t.message}")
                lost(mySession, "Não foi possível manter a conexão Live com o Gemini.")
            }
            override fun onClosing(ws: WebSocket, code: Int, reason: String) { ws.close(code, null) }
            override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                android.util.Log.w("JarvisLive", "closed $code $reason")
                lost(mySession, if (reason.isNotBlank()) "Gemini Live encerrou a sessão: ${reason.take(200)}" else "A sessão Live foi encerrada.")
            }
        })
    }

    private fun setup(voice: String, model: String): String {
        val resumption = JSONObject().apply { if (resumeHandle.isNotBlank()) put("handle", resumeHandle) }
        return JSONObject().put("setup", JSONObject()
            .put("model", "models/$model")
            .put("generationConfig", JSONObject().put("responseModalities", JSONArray().put("AUDIO"))
                .put("speechConfig", JSONObject().put("voiceConfig", JSONObject().put("prebuiltVoiceConfig", JSONObject().put("voiceName", voice)))))
            .put("systemInstruction", JSONObject().put("parts", JSONArray().put(JSONObject().put("text", instruction()))))
            .put("tools", JSONArray().put(JSONObject().put("functionDeclarations", upperTypes(tools()))))
            .put("outputAudioTranscription", JSONObject())
            .put("contextWindowCompression", JSONObject().put("slidingWindow", JSONObject()))
            .put("sessionResumption", resumption)).toString()
    }

    /** O protocolo Live espera os tipos do esquema em maiúsculas (STRING, OBJECT…). */
    private fun upperTypes(value: JSONArray): JSONArray = convert(value) as JSONArray
    private fun convert(value: Any?): Any? = when (value) {
        is JSONArray -> JSONArray().also { out -> for (i in 0 until value.length()) out.put(convert(value.get(i))) }
        is JSONObject -> JSONObject().also { out ->
            for (key in value.keys()) {
                val item = value.get(key)
                out.put(key, if (key == "type" && item is String) item.uppercase() else convert(item))
            }
        }
        else -> value
    }

    private fun handle(id: Int, ws: WebSocket, raw: String) {
        val message = runCatching { JSONObject(raw) }.getOrNull() ?: return
        synchronized(lock) {
            if (id != session) return
            if (message.has("setupComplete")) {
                ready = true
                pending?.let { ws.send(it) }; pending = null
            }
            message.optJSONObject("sessionResumptionUpdate")?.let {
                if (it.optBoolean("resumable") && it.optString("newHandle").isNotBlank()) resumeHandle = it.optString("newHandle")
            }
            if (message.has("goAway")) expiring = true
            message.optJSONObject("error")?.let { error ->
                android.util.Log.w("JarvisLive", "error ${error.toString().take(300)}")
                turn?.let { finishLocked(Outcome(null, "Gemini Live recusou o pedido.", it.toolsRan), close = true) }
                return
            }
            message.optJSONObject("toolCall")?.optJSONArray("functionCalls")?.let { calls -> runTools(id, ws, calls) }
            val content = message.optJSONObject("serverContent") ?: return
            val current = turn
            current?.lastServer = android.os.SystemClock.elapsedRealtime()
            content.optJSONObject("outputTranscription")?.optString("text")?.let { current?.text?.append(it) }
            val parts = content.optJSONObject("modelTurn")?.optJSONArray("parts")
            if (parts != null && current != null) for (i in 0 until parts.length()) {
                val inline = parts.getJSONObject(i).optJSONObject("inlineData") ?: continue
                val mime = inline.optString("mimeType")
                if (!mime.startsWith("audio/")) continue
                if (!current.firstAudio) {
                    current.firstAudio = true
                    android.util.Log.d("JarvisLatency", "live_first_audio_ms=${android.os.SystemClock.elapsedRealtime() - current.started}")
                }
                if (store.get("speak", "true") == "true") {
                    val rate = Regex("rate=(\\d+)").find(mime)?.groupValues?.get(1)?.toIntOrNull() ?: 24000
                    GeminiVoice.streamAudio(Base64.decode(inline.getString("data"), Base64.NO_WRAP), rate)
                }
            }
            if (content.optBoolean("turnComplete") && current != null) {
                android.util.Log.d("JarvisLatency", "live_turn_ms=${android.os.SystemClock.elapsedRealtime() - current.started}")
                finishLocked(Outcome(current.text.toString().trim().replace(Regex("\\s+"), " "), null, current.toolsRan), close = expiring)
            }
        }
    }

    private fun runTools(id: Int, ws: WebSocket, calls: JSONArray) {
        val current = turn ?: return
        current.toolsRan = true
        // A fala depois da ação chega como um novo trecho; separa as frases no chat.
        if (current.text.isNotEmpty() && !current.text.endsWith(" ")) current.text.append(' ')
        AppState.phase = "PENSANDO"; AppState.update()
        toolWorker.execute {
            val responses = JSONArray()
            val images = mutableListOf<String>()
            for (i in 0 until calls.length()) {
                val call = calls.getJSONObject(i)
                val name = call.optString("name")
                val started = android.os.SystemClock.elapsedRealtime()
                val result = runCatching { runTool(name, call.optJSONObject("args") ?: JSONObject()) }
                    .getOrElse { PhoneTools.result(false, it.message ?: "Falha na ferramenta.") }
                android.util.Log.d("JarvisLatency", "live_tool=$name tool_ms=${android.os.SystemClock.elapsedRealtime() - started}")
                compact(result); result.optJSONObject("observation")?.let { compact(it) }
                android.util.Log.d("JarvisLive", "tool_response_chars=${result.toString().length}")
                val image = result.optString("image"); result.remove("image")
                if (image.isNotEmpty()) { images.add(image); result.put("image_note", "A captura foi enviada como imagem logo antes desta resposta.") }
                responses.put(JSONObject().put("id", call.optString("id")).put("name", name).put("response", result))
            }
            synchronized(lock) {
                if (id != session || turn !== current) return@execute
                // A captura vai como quadro de vídeo, que a sessão Live consegue enxergar.
                images.forEach { ws.send(JSONObject().put("realtimeInput", JSONObject().put("video", JSONObject().put("mimeType", "image/jpeg").put("data", it))).toString()) }
                ws.send(JSONObject().put("toolResponse", JSONObject().put("functionResponses", responses)).toString())
                current.lastServer = android.os.SystemClock.elapsedRealtime()
            }
            // Se o Gemini ficar mudo depois da ação, avisa em vez de deixar o usuário esperando.
            main.postDelayed({ synchronized(lock) {
                if (turn === current && id == session && android.os.SystemClock.elapsedRealtime() - current.lastServer >= 24_000)
                    finishLocked(Outcome(null, "O Gemini Live não respondeu depois da ação.", true), close = true)
            } }, 25_000)
        }
    }

    /**
     * Leituras de tela grandes (lista do WhatsApp, por exemplo) travam a sessão Live.
     * Mantém só o essencial: até 60 elementos com id, texto curto, posição e se é tocável/editável.
     */
    private fun compact(result: JSONObject) {
        val nodes = result.optJSONArray("nodes") ?: return
        val small = JSONArray()
        for (i in 0 until nodes.length()) {
            if (small.length() >= 60) break
            val node = nodes.optJSONObject(i) ?: continue
            val text = node.optString("text").take(80)
            val clickable = node.optBoolean("clickable"); val editable = node.optBoolean("editable"); val scrollable = node.optBoolean("scrollable")
            if (text.isBlank() && !clickable && !editable && !scrollable) continue
            small.put(JSONObject().put("element_id", node.optString("element_id")).put("text", text).put("bounds", node.optJSONArray("bounds"))
                .apply {
                    node.optString("resource_id").substringAfterLast("/").takeIf { it.isNotBlank() }?.let { put("id", it) }
                    if (clickable) put("clickable", true); if (editable) put("editable", true); if (scrollable) put("scrollable", true)
                })
        }
        result.put("nodes", small)
        if (nodes.length() > small.length()) result.put("nodes_omitted", nodes.length() - small.length())
        result.remove("visible_text") // os textos já estão nos elementos
    }

    private fun lost(id: Int, reason: String) {
        synchronized(lock) {
            if (id != session) return
            socket = null; ready = false; pending = null
            turn?.let { finishLocked(Outcome(null, reason, it.toolsRan), close = false) }
        }
    }

    private fun finishLocked(outcome: Outcome, close: Boolean) {
        val current = turn ?: return
        if (current.finished) return
        current.finished = true; turn = null
        if (outcome.error == null) GeminiVoice.finishStream() else GeminiVoice.stop()
        if (close) closeLocked() else { main.removeCallbacks(idleClose); main.postDelayed(idleClose, IDLE_CLOSE_MS) }
        toolWorker.execute { current.done(outcome) }
    }

    private fun closeLocked() {
        session++
        socket?.cancel(); socket = null; ready = false; pending = null
    }
}
