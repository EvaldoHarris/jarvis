package com.evaldoharris.jarvis

import android.content.Context
import org.json.JSONObject
import org.vosk.Model
import org.vosk.Recognizer
import java.io.File
import java.util.concurrent.Executors

/**
 * Detector offline da palavra Jarvis (Vosk). O reconhecedor do Google costuma devolver vazio
 * para uma palavra curta e solta; este detector escuta o mesmo áudio e só procura o nome.
 * O modelo pequeno de português não conhece "jarvis", então usamos as palavras de som mais próximo.
 */
internal class WakeSpotter(private val onWake: (String) -> Unit) {
    companion object {
        /** Palavras que o modelo conhece e que soam como "Jarvis". */
        private val WAKE = setOf("jarbas", "chaves", "já vis", "harvey")
        /** Iscas: palavras parecidas que NÃO devem ativar (o detector escolhe estas em vez do nome). */
        private val DECOYS = listOf("chave", "jarra", "jarros", "jair", "jairo", "xavier", "davis", "travis", "avis", "já", "vi", "javé")
        private val GRAMMAR = (WAKE + DECOYS + "[unk]").joinToString(",", "[", "]") { "\"$it\"" }
        private const val MIN_CONFIDENCE = 0.55
        private val loader = Executors.newSingleThreadExecutor()
        @Volatile private var model: Model? = null

        /** Copia o modelo dos assets uma única vez e o carrega em memória (alguns segundos na primeira vez). */
        fun preload(context: Context) {
            if (model != null) return
            val app = context.applicationContext
            loader.execute {
                if (model != null) return@execute
                runCatching {
                    val target = File(app.filesDir, "vosk-pt")
                    val version = app.assets.open("vosk-pt/VERSION").bufferedReader().readText().trim()
                    val marker = File(target, "VERSION")
                    if (!marker.exists() || marker.readText().trim() != version) {
                        target.deleteRecursively(); copyAssets(app, "vosk-pt", target)
                    }
                    org.vosk.LibVosk.setLogLevel(org.vosk.LogLevel.WARNINGS)
                    model = Model(target.absolutePath)
                    android.util.Log.d("JarvisWake", "spotter_model_ready")
                }.onFailure { android.util.Log.w("JarvisWake", "spotter_model_failed ${it.message}") }
            }
        }
        private fun copyAssets(context: Context, path: String, target: File) {
            val children = context.assets.list(path).orEmpty()
            if (children.isEmpty()) {
                target.parentFile?.mkdirs()
                context.assets.open(path).use { input -> target.outputStream().use { input.copyTo(it) } }
                return
            }
            target.mkdirs()
            for (child in children) copyAssets(context, "$path/$child", File(target, child))
        }
    }

    private var recognizer: Recognizer? = null
    private var lastWake = 0L
    private var lastPartial = ""

    /** Recebe áudio PCM 16 kHz mono do microfone contínuo (na thread do microfone). */
    @Synchronized fun feed(buffer: ByteArray, count: Int) {
        val current = model ?: return
        val rec = recognizer ?: Recognizer(current, 16000f, GRAMMAR).apply { setWords(true) }.also { recognizer = it }
        if (rec.acceptWaveForm(buffer, count)) {
            lastPartial = ""
            inspectFinal(rec.result)
        } else {
            val partial = runCatching { JSONObject(rec.partialResult).optString("partial") }.getOrDefault("")
            if (partial != lastPartial) { lastPartial = partial; inspectPartial(partial) }
        }
    }

    private fun leadingWake(text: String): String? {
        val words = text.split(" ").filter { it.isNotBlank() && it != "[unk]" }
        if (words.isEmpty()) return null
        val two = words.take(2).joinToString(" ")
        return when { two in WAKE -> two; words[0] in WAKE -> words[0]; else -> null }
    }

    /** Resultado parcial: arma rápido, ainda durante a fala, se o nome vier no início. */
    private fun inspectPartial(text: String) {
        val wake = leadingWake(text) ?: return
        android.util.Log.d("JarvisWakeText", "spotter_partial=$text")
        fire(wake)
    }

    private fun inspectFinal(raw: String) {
        val json = runCatching { JSONObject(raw) }.getOrNull() ?: return
        val text = json.optString("text")
        val words = json.optJSONArray("result")
        val first = words?.optJSONObject(0)
        if (text.isBlank()) return
        android.util.Log.d("JarvisWakeText", "spotter_final='$text' conf=${first?.optDouble("conf")}")
        val wake = leadingWake(text) ?: return
        if ((first?.optDouble("conf", 1.0) ?: 1.0) < MIN_CONFIDENCE) return
        fire(wake)
    }

    private fun fire(word: String) {
        val now = System.currentTimeMillis()
        if (now - lastWake < 2500) return
        lastWake = now
        onWake(word)
    }

    fun close() { runCatching { recognizer?.close() }; recognizer = null }
}
