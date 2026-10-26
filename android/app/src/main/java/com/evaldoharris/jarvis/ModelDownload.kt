package com.evaldoharris.jarvis

import android.content.Context
import okhttp3.Call
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.IOException
import java.security.MessageDigest
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.util.concurrent.TimeUnit

/** Downloads to a separate file; only a complete, authenticated artifact replaces the model. */
object VerifiedModelTransfer {
    fun transfer(call: Call, target: File, expectedBytes: Long, sha256: String,
                 cancelled: () -> Boolean = { false }, progress: (Long) -> Unit = {}) {
        target.parentFile?.mkdirs()
        val temporary = File(target.parentFile, target.name + ".download")
        try {
            call.execute().use { response ->
                check(response.isSuccessful) { "Servidor do modelo respondeu HTTP ${response.code}." }
                val body = response.body ?: error("Download sem conteúdo.")
                val hash = MessageDigest.getInstance("SHA-256")
                var total = 0L
                body.byteStream().use { source -> temporary.outputStream().use { output ->
                    val buffer = ByteArray(256 * 1024)
                    while (true) {
                        if (cancelled()) throw IOException("Download cancelado.")
                        val count = source.read(buffer)
                        if (count < 0) break
                        total += count
                        check(total <= expectedBytes) { "Tamanho do modelo inesperado." }
                        hash.update(buffer, 0, count); output.write(buffer, 0, count); progress(total)
                    }
                } }
                check(total == expectedBytes) { "Download incompleto. Tente novamente." }
                val actual = hash.digest().joinToString("") { "%02x".format(it) }
                check(actual == sha256) { "Verificação do modelo falhou. O arquivo não foi instalado." }
                if (cancelled()) throw IOException("Download cancelado.")
                Files.move(temporary.toPath(), target.toPath(), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
            }
        } finally { temporary.delete() }
    }
}

object ModelDownload {
    const val BYTES = 977184032L
    const val SHA256 = "2a72330b504a6596d53a2c00923c57173b10f1b83e6a541213ffec08d1fc5de8"
    const val PAGE = "https://huggingface.co/litert-community/Qwen3-1.7B"
    private const val URL = "$PAGE/resolve/79bf0667b32ae025b972e5fe555fe72ca6e8816c/Qwen3-1.7B_dynamic_wi4b32_afp32.litertlm"
    @Volatile var running = false; private set
    @Volatile var bytes = 0L; private set
    @Volatile var message = ""; private set
    @Volatile private var cancelled = false
    @Volatile private var call: Call? = null
    @Synchronized fun start(context: Context) {
        if (running) return
        val app = context.applicationContext
        running = true; cancelled = false; bytes = 0; message = "Preparando download…"
        Thread({
            try {
                val target = LocalAi.model(app)
                check(app.filesDir.usableSpace > BYTES + 128L * 1024 * 1024) { "Libere pelo menos 1,1 GB para baixar o modelo." }
                val request = OkHttpClient.Builder().connectTimeout(20, TimeUnit.SECONDS).readTimeout(60, TimeUnit.SECONDS)
                    .build().newCall(Request.Builder().url(URL).build())
                call = request
                if (cancelled) request.cancel()
                VerifiedModelTransfer.transfer(request, target, BYTES, SHA256, { cancelled }) {
                    bytes = it; message = "Baixando modelo…"
                }
                message = "Modelo instalado e verificado. Escolha IA local ou Automático e salve."
            } catch (e: Exception) {
                message = if (cancelled) "Download cancelado. O modelo anterior foi preservado." else "Falha no download: ${e.message}"
            } finally { call = null; running = false }
        }, "jarvis-model-download").start()
    }
    fun cancel() { cancelled = true; call?.cancel() }
}
