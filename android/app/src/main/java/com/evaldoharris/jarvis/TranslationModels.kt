package com.evaldoharris.jarvis

import android.content.Context
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.common.model.DownloadConditions
import com.google.mlkit.common.model.RemoteModelManager
import com.google.mlkit.nl.translate.TranslateLanguage
import com.google.mlkit.nl.translate.TranslateRemoteModel
import com.google.mlkit.nl.translate.Translation
import com.google.mlkit.nl.translate.TranslatorOptions
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.util.concurrent.TimeUnit
import java.util.zip.ZipInputStream

object TranslationModels {
    private const val MODEL = "vosk-model-small-en-us-0.15"
    fun path(context: Context) = File(context.filesDir, "video-translation/$MODEL")
    private fun speechReady(context: Context) = File(path(context), "am/final.mdl").isFile && File(path(context), "conf/model.conf").isFile
    fun ready(context: Context): Boolean {
        if (!speechReady(context)) return false
        val manager = RemoteModelManager.getInstance()
        return listOf("en", "pt").all {
            Tasks.await(manager.isModelDownloaded(TranslateRemoteModel.Builder(it).build()), 20, TimeUnit.SECONDS)
        }
    }
    fun prepare(context: Context, progress: (String) -> Unit) {
        if (!speechReady(context)) {
            progress("Baixando reconhecimento de inglês (cerca de 40 MB)…")
            val root = File(context.filesDir, "video-translation").apply { mkdirs() }
            val stage = File(root, "staging").apply { deleteRecursively(); mkdirs() }
            try {
                val client = OkHttpClient.Builder().connectTimeout(20, TimeUnit.SECONDS).readTimeout(40, TimeUnit.SECONDS).callTimeout(8, TimeUnit.MINUTES).build()
                client.newCall(Request.Builder().url("https://alphacephei.com/vosk/models/$MODEL.zip").build()).execute().use { response ->
                    check(response.isSuccessful) { "Falha ao baixar modelo: HTTP ${response.code}" }
                    val body = response.body ?: error("Modelo vazio")
                    ZipInputStream(body.byteStream()).use { zip ->
                        var total = 0L; var entries = 0
                        while (true) {
                            check(!Thread.currentThread().isInterrupted) { "Preparação cancelada" }
                            val entry = zip.nextEntry ?: break
                            check(++entries <= 300) { "Arquivo de modelo inválido" }
                            val target = File(stage, entry.name).canonicalFile
                            check(target.path.startsWith(stage.canonicalPath + File.separator)) { "Caminho inválido no modelo" }
                            if (entry.isDirectory) target.mkdirs() else {
                                target.parentFile?.mkdirs()
                                target.outputStream().use { output ->
                                    val buffer = ByteArray(32768)
                                    while (true) {
                                        check(!Thread.currentThread().isInterrupted) { "Preparação cancelada" }
                                        val n = zip.read(buffer); if (n < 0) break
                                        total += n; check(total <= 300L * 1024 * 1024) { "Modelo excedeu o tamanho permitido" }
                                        output.write(buffer, 0, n)
                                    }
                                }
                            }
                        }
                    }
                }
                check(File(stage, "$MODEL/am/final.mdl").isFile && File(stage, "$MODEL/conf/model.conf").isFile) { "Modelo incompleto" }
                path(context).deleteRecursively()
                check(File(stage, MODEL).renameTo(path(context))) { "Não foi possível instalar o modelo" }
            } finally { stage.deleteRecursively() }
        }
        progress("Preparando tradução local de inglês para português…")
        Translation.getClient(TranslatorOptions.Builder().setSourceLanguage(TranslateLanguage.ENGLISH)
            .setTargetLanguage(TranslateLanguage.PORTUGUESE).build()).use {
            Tasks.await(it.downloadModelIfNeeded(DownloadConditions.Builder().build()), 8, TimeUnit.MINUTES)
        }
        check(ready(context)) { "Os modelos ainda não estão prontos" }
        progress("Modelos prontos. Reconhecimento e tradução funcionarão offline.")
    }
}
