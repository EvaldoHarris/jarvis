package com.evaldoharris.jarvis

import okhttp3.Call
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class GeminiUnavailable(message: String) : IllegalStateException(message)

class GeminiApi(private val endpoint: String = "https://generativelanguage.googleapis.com",
                private val onCall: (Call) -> Unit = {}, private val cancelled: () -> Boolean = { false },
                private val onRetry: (Int) -> Unit = {}) {
    companion object {
        private val client = OkHttpClient.Builder().connectTimeout(10, TimeUnit.SECONDS).readTimeout(45, TimeUnit.SECONDS).build()
    }
    private fun execute(request: Request, key: String, model: String): Pair<Int, JSONObject> {
        repeat(3) { attempt ->
        check(!cancelled()) { "Pedido interrompido." }
        val call = client.newCall(request); onCall(call)
        val result = call.execute().use { response ->
            val raw = response.body?.string().orEmpty()
            val body = try { JSONObject(raw) } catch (_: Exception) { JSONObject() }
            response.code to body
        }
        if (result.first == 503 && attempt < 2) {
            onRetry(attempt + 1)
            // Pausas curtas: sobrecarga do Google costuma passar em menos de 1 s.
            val pause = (350L shl attempt) + kotlin.random.Random.nextLong(0, 150)
            val until = System.nanoTime() + pause * 1_000_000
            while (System.nanoTime() < until) {
                check(!cancelled()) { "Pedido interrompido." }
                Thread.sleep(80)
            }
        } else {
            if (result.first !in 200..299 && result.first != 404)
                throw if (result.first in listOf(429, 500, 502, 503, 504)) GeminiUnavailable(GeminiModelPolicy.error(result.first, model, detail(result.second, key)))
                else IllegalStateException(GeminiModelPolicy.error(result.first, model, detail(result.second, key)))
            return result
        }
        }
        error("O modelo está temporariamente ocupado. Tente novamente em instantes.")
    }
    private fun detail(body: JSONObject, key: String): String = body.optJSONObject("error")?.optString("message").orEmpty()
        .replace(key, "[chave oculta]").replace(Regex("AIza[0-9A-Za-z_-]{20,}"), "[chave oculta]")

    fun models(key: String): List<String> {
        require(key.isNotBlank()) { "Preencha sua chave Gemini antes de buscar modelos." }
        val models = mutableListOf<String>()
        var page = ""
        repeat(5) {
            val url = "$endpoint/v1beta/models".toHttpUrl().newBuilder().addQueryParameter("pageSize", "1000")
                .apply { if (page.isNotBlank()) addQueryParameter("pageToken", page) }.build()
            val (code, body) = execute(Request.Builder().url(url).header("x-goog-api-key", key).build(), key, "listagem de modelos")
            check(code == 200) { GeminiModelPolicy.error(code, "listagem de modelos", detail(body, key)) }
            val items = body.optJSONArray("models")
            if (items != null) for (index in 0 until items.length()) {
                val item = items.getJSONObject(index)
                val methods = item.optJSONArray("supportedGenerationMethods")
                val supports = methods != null && (0 until methods.length()).any { methods.optString(it) == "generateContent" }
                val name = item.optString("name").removePrefix("models/")
                if (supports && GeminiModelPolicy.chatModel(name)) models.add(GeminiModelPolicy.normalize(name))
            }
            page = body.optString("nextPageToken")
            if (page.isBlank()) return models.distinct().sorted()
        }
        return models.distinct().sorted()
    }

    private fun post(key: String, model: String, body: JSONObject): Pair<Int, JSONObject> {
        val request = Request.Builder().url("$endpoint/v1beta/models/$model:generateContent")
            .header("x-goog-api-key", key).post(body.toString().toRequestBody("application/json".toMediaType())).build()
        return execute(request, key, model)
    }

    /** Raciocínio mínimo: comandos do celular precisam de rapidez, não de longas deliberações. */
    private fun thinkingFor(model: String): JSONObject? = when {
        model.startsWith("gemini-2.5-flash") -> JSONObject().put("thinkingBudget", 0)
        model.startsWith("gemini-2.5-pro") -> JSONObject().put("thinkingBudget", 128)
        model.startsWith("gemini-3") || model == "gemini-flash-latest" || model == "gemini-flash-lite-latest" -> JSONObject().put("thinkingLevel", "low")
        else -> null
    }
    private fun withThinking(payload: JSONObject, model: String, enabled: Boolean): JSONObject {
        val thinking = thinkingFor(model)
        if (!enabled || thinking == null || payload.optJSONObject("generationConfig")?.has("thinkingConfig") == true) return payload
        val copy = JSONObject(payload.toString())
        val config = copy.optJSONObject("generationConfig") ?: JSONObject().also { copy.put("generationConfig", it) }
        config.put("thinkingConfig", thinking)
        return copy
    }

    fun generate(key: String, preferred: String, payload: JSONObject, changed: (String) -> Unit): JSONObject {
        var model = GeminiModelPolicy.normalize(preferred)
        val rejected = mutableSetOf<String>()
        var available: List<String>? = null
        var fastThinking = true
        repeat(3) { attempt ->
            var (code, response) = post(key, model, withThinking(payload, model, fastThinking))
            // Se o modelo recusar a configuração de raciocínio, repete sem ela.
            if (code == 400 && fastThinking && thinkingFor(model) != null) { fastThinking = false; post(key, model, payload).let { code = it.first; response = it.second } }
            if (code in 200..299) { if (model != GeminiModelPolicy.normalize(preferred)) changed(model); return response }
            rejected.add(model)
            val previous = model
            if (attempt < 2) {
                if (available == null) available = models(key)
                GeminiModelPolicy.fallback(model, available!!, rejected)?.let { model = it }
            }
            if (model == previous) throw IllegalStateException(GeminiModelPolicy.error(code, model, detail(response, key)))
        }
        error("Não foi encontrado um modelo Flash acessível. Use Buscar modelos nas configurações.")
    }
}
