package com.evaldoharris.jarvis

import android.content.Context
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest
import java.util.concurrent.TimeUnit
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

class TuyaClient(context: Context, private val testEndpoint: String? = null) {
    private val store = SecureStore(context)
    private val client = OkHttpClient.Builder().connectTimeout(6, TimeUnit.SECONDS).readTimeout(12, TimeUnit.SECONDS)
        .retryOnConnectionFailure(false).followRedirects(false).followSslRedirects(false).build()
    private var token = ""
    private fun endpoint(): String = testEndpoint ?: when(store.get("tuya_region", "us")) {
        "us" -> "https://openapi.tuyaus.com"
        "us-e" -> "https://openapi-ueaz.tuyaus.com"
        "eu" -> "https://openapi.tuyaeu.com"
        "eu-w" -> "https://openapi-weaz.tuyaeu.com"
        "cn" -> "https://openapi.tuyacn.com"
        "in" -> "https://openapi.tuyain.com"
        else -> error("Região Tuya inválida.")
    }
    private fun request(method: String, path: String, body: JSONObject? = null, auth: Boolean = true): JSONObject {
        val key = store.get("tuya_key"); val secret = store.get("tuya_secret")
        require(key.isNotBlank() && secret.isNotBlank()) { "Configure a Tuya em CASA ou importe a configuração do PC." }
        if (auth && token.isEmpty()) token = request("GET", "/v1.0/token?grant_type=1", auth = false).getJSONObject("result").getString("access_token")
        val text = body?.toString().orEmpty(); val time = System.currentTimeMillis().toString()
        val signature = sign(key, secret, if (auth) token else "", time, method, path, text)
        val request = Request.Builder().url(endpoint() + path).header("client_id", key).header("t", time).header("sign_method", "HMAC-SHA256").header("sign", signature)
            .apply { if (auth) header("access_token", token) }
            .method(method, if (method == "GET") null else text.toRequestBody("application/json".toMediaType())).build()
        client.newCall(request).execute().use { response ->
            check(response.isSuccessful) { "Tuya respondeu HTTP ${response.code}; a ação não foi repetida." }
            val bytes = response.body?.byteStream()?.readBounded(1_000_000) ?: ByteArray(0)
            check(bytes.size <= 1_000_000) { "Resposta Tuya maior que o limite." }
            // Read a bounded body without including vendor payloads or credentials in errors.
            val result = JSONObject(bytes.toString(Charsets.UTF_8))
            check(result.optBoolean("success")) { "Tuya recusou o pedido (código ${result.optString("code", "desconhecido")}); confira região, vínculo e permissões do projeto." }
            return result
        }
    }
    private fun devices(): List<JSONObject> {
        val result = mutableListOf<JSONObject>(); var cursor = ""
        repeat(10) {
            val path = if (cursor.isEmpty()) "/v1.0/iot-01/associated-users/devices?size=50" else "/v1.0/iot-01/associated-users/devices?last_row_key=${java.net.URLEncoder.encode(cursor,"UTF-8")}&size=50"
            val response = request("GET", path).getJSONObject("result")
            val values = response.optJSONArray("devices") ?: JSONArray()
            for (i in 0 until values.length()) result.add(values.getJSONObject(i))
            if (!response.optBoolean("has_more")) return result
            cursor = response.getString("last_row_key")
        }
        error("A conta retornou mais de 500 dispositivos; refine a configuração Tuya.")
    }
    private fun status(id: String): JSONObject {
        val result = JSONObject(); val values = request("GET", "/v1.0/devices/$id/status").getJSONArray("result")
        for (i in 0 until values.length()) values.getJSONObject(i).let { result.put(it.getString("code"), it.get("value")) }
        return result
    }
    fun execute(action: String, args: JSONObject): JSONObject {
        require(action in listOf("list", "status", "on", "off", "brightness")) { "Ação Tuya desconhecida." }
        if (action == "brightness") require(args.optInt("percent", -1) in 1..100) { "Brilho deve estar entre 1 e 100%." }
        val devices = devices()
        if (action == "list") return PhoneTools.result(true).put("devices", JSONArray().apply { devices.forEach { put(JSONObject().put("id", it.optString("id")).put("name", it.optString("name")).put("online", it.optBoolean("online"))) } })
        val wanted = args.optString("name")
        val matches = devices.filter { it.optString("name").equals(wanted, true) || it.optString("id") == wanted }
        require(wanted.isNotBlank() && matches.size == 1) { "Escolha um único dispositivo pelo nome exato ou ID retornado por list." }
        val device = matches.single(); val id = device.getString("id")
        require(id.matches(Regex("[a-zA-Z0-9_-]{1,100}")))
        val state = status(id)
        if (action == "status") return PhoneTools.result(true).put("name", device.optString("name")).put("online", device.optBoolean("online")).put("status", state)
        check(device.optBoolean("online")) { "Dispositivo offline; nenhum comando foi enviado." }
        val commands = JSONArray()
        val code: String; val value: Any
        if (action == "brightness") {
            code = when { state.has("bright_value_v2") -> "bright_value_v2"; state.has("bright_value") -> "bright_value"; else -> error("Este dispositivo não oferece ajuste de brilho.") }
            val percent = args.getInt("percent")
            value = if (code == "bright_value_v2") 10 + (990 * percent / 100) else 25 + (230 * percent / 100)
        } else {
            code = listOf("switch_led", "switch_1", "switch", "led_switch").firstOrNull { state.has(it) } ?: error("Este dispositivo não oferece um interruptor de luz compatível.")
            value = action == "on"
        }
        commands.put(JSONObject().put("code", code).put("value", value))
        val sent = request("POST", "/v1.0/devices/$id/commands", JSONObject().put("commands", commands))
        if (!sent.optBoolean("result")) return PhoneTools.result(false,"Tuya não aceitou o comando. Nenhuma repetição foi feita.")
        val after = runCatching { status(id) }.getOrNull()
        return PhoneTools.result(true).put("accepted", true).put("verified", after?.opt(code) == value).put("name", device.optString("name"))
            .put("note", "Aceito pela Tuya; verified informa se o estado consultado confirmou a alteração.")
    }
    companion object {
        fun sign(key: String, secret: String, token: String, time: String, method: String, path: String, body: String): String {
            fun hex(bytes: ByteArray) = bytes.joinToString("") { "%02x".format(it.toInt() and 255) }
            val digest = hex(MessageDigest.getInstance("SHA-256").digest(body.toByteArray(Charsets.UTF_8)))
            val canonical = "$method\n$digest\n\n$path"
            val mac = Mac.getInstance("HmacSHA256").apply { init(SecretKeySpec(secret.toByteArray(Charsets.UTF_8), "HmacSHA256")) }
            return hex(mac.doFinal((key + token + time + canonical).toByteArray(Charsets.UTF_8))).uppercase(java.util.Locale.ROOT)
        }
    }
}
