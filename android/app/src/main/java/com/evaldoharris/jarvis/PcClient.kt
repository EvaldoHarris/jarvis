package com.evaldoharris.jarvis

import android.content.Context
import android.content.Intent
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import java.util.UUID

class PcClient(private val context: Context) {
    val store = SecureStore(context)
    val client = OkHttpClient.Builder().connectTimeout(6, TimeUnit.SECONDS).readTimeout(25, TimeUnit.SECONDS).pingInterval(20, TimeUnit.SECONDS).build()
    fun address(): String = ServerAddress.normalize(store.get("pc_url"))
    fun post(path: String, body: JSONObject, token: String = ""): JSONObject {
        val request = Request.Builder().url(address() + path)
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .apply { if (token.isNotEmpty()) header("Authorization", "Bearer $token") }.build()
        client.newCall(request).execute().use { response ->
            if (response.code == 401) throw Unauthorized()
            check(response.isSuccessful) { "PC não respondeu ao pedido (HTTP ${response.code})." }
            return JSONObject(response.body?.string() ?: "{}")
        }
    }
    fun pair(pin: String) {
        require(pin.matches(Regex("[A-Z2-9]{8}"))) { "Use a chave de 8 caracteres mostrada no PC." }
        val reply = post("/login", JSONObject().put("pin", pin))
        store.put("pc_device_token", reply.getString("device_token"))
        store.put("pc_token", reply.getString("token"))
    }
    fun renew(): String {
        val device = store.get("pc_device_token")
        require(device.isNotEmpty()) { "Faça o pareamento com o PC." }
        return post("/api/device-login", JSONObject().put("device_token", device)).getString("token").also { store.put("pc_token", it) }
    }
    fun pairedPost(path: String, body: JSONObject = JSONObject()): JSONObject {
        var token = store.get("pc_token")
        if (token.isEmpty()) token = renew()
        return try { post(path, body, token) } catch (_: Unauthorized) { post(path, body, renew()) }
    }
    @Synchronized fun command(text: String): JSONObject {
        require(text.isNotBlank() && text.length <= 12000)
        context.startForegroundService(Intent(context, PhoneControlService::class.java).setAction("listen_reply"))
        val deadline = System.currentTimeMillis() + 12000
        while (!AppState.pcReady && System.currentTimeMillis() < deadline) Thread.sleep(80)
        check(AppState.pcReady) { "O PC não conectou ao canal de respostas. Confira o endereço e a rede/VPN." }
        val requestId = UUID.randomUUID().toString()
        AppState.expectedPhoneReply = requestId
        AppState.phoneReplyDeadline = System.currentTimeMillis() + 90000
        val body = JSONObject().put("text", text).put("reply_device", store.get("device_id")).put("reply_id", requestId)
        var token = store.get("pc_token")
        if (token.isEmpty()) token = renew()
        try { post("/api/command", body, token) }
        catch (_: Unauthorized) { post("/api/command", body, renew()) }
        return JSONObject().put("ok", true).put("accepted", true).put("executed", false)
            .put("note", "Pedido enviado ao assistente do PC. Aguarde o resultado; envio não confirma execução.")
    }
    class Unauthorized : Exception("Pareamento recusado ou sessão expirada.")
}
