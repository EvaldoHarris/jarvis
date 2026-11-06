package com.evaldoharris.jarvis

import android.content.Context
import android.media.MediaPlayer
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit

/** Serializes the local alert voice and PC PCM so neither cuts the other off. */
internal class PresencePhoneAudio(private val context: Context) : AutoCloseable {
    private data class Item(val id: String = "", val pcm: ByteArray? = null, val rate: Int = 24000,
                            val warning: Boolean = false, val end: Boolean = false, val text: String = "", val generation: Int)
    private val queue = LinkedBlockingQueue<Item>(512)
    private val worker = Executors.newSingleThreadExecutor()
    @Volatile private var generation = 0
    @Volatile private var closed = false
    @Volatile private var pcm: PcmPlayback? = null
    @Volatile private var media: MediaPlayer? = null
    @Volatile internal var playedWarnings = 0
        private set
    @Volatile internal var playedStreams = 0
        private set
    @Volatile internal var lastError = ""
        private set
    init { worker.execute { run() } }
    fun warning() = offer(Item(warning = true, generation = generation))
    fun text(text: String) = offer(Item(text = text.take(8000), generation = generation))
    fun audio(id: String, data: ByteArray, rate: Int) = offer(Item(id, data, rate, generation = generation))
    fun finish(id: String) = offer(Item(id = id, end = true, generation = generation))
    private fun offer(item: Item) {
        if (!closed && !queue.offer(item)) { stop(); AppState.message("SYS", "Áudio remoto excedeu a fila; confira a resposta no histórico.") }
    }
    fun stop() {
        generation++; queue.clear(); pcm?.stop(); pcm = null
        try { media?.stop() } catch (_: Exception) { }
        AppState.audioBusy = false; AppState.update()
    }
    override fun close() { closed = true; stop(); worker.shutdownNow() }
    private fun run() {
        var voice: TranslationNeuralVoice? = null
        var current = ""
        var drained: CountDownLatch? = null
        try {
            while (!closed) {
                val item = queue.poll(100, TimeUnit.MILLISECONDS) ?: continue
                if (item.generation != generation) continue
                if (item.warning || item.text.isNotBlank()) {
                    val file = File.createTempFile("presence-warning-", ".wav", context.cacheDir)
                    try {
                        AppState.audioBusy = true; AppState.update()
                        if (voice == null) voice = TranslationNeuralVoice(context)
                        if (!voice.synthesize(if (item.warning) PresencePreviewState.NOTICE else item.text, file) { closed || item.generation != generation }) continue
                        val player = MediaPlayer(); media = player
                        try {
                            player.setAudioAttributes(AssistantAudio.attributes())
                            player.setDataSource(file.absolutePath); player.prepare()
                            if (closed || item.generation != generation) continue
                            player.start()
                            while (!closed && item.generation == generation && player.isPlaying) Thread.sleep(30)
                            if (item.warning && !closed && item.generation == generation) playedWarnings++
                        } finally { media = null; player.release() }
                    } catch (e: Exception) { lastError = "warning: ${e.javaClass.simpleName}"; AppState.message("SYS", "A voz local do aviso falhou; a resposta do PC e a imagem continuam disponíveis.") }
                    finally { file.delete(); AppState.audioBusy = false; AppState.lastAudioEnd = System.currentTimeMillis(); AppState.update() }
                } else if (item.end) {
                    if (current == item.id) {
                        pcm?.finish()
                        while (!closed && item.generation == generation && drained?.await(100, TimeUnit.MILLISECONDS) == false) { }
                        if (!closed && item.generation == generation) playedStreams++
                        pcm = null; current = ""; AppState.audioBusy = false
                        if (AppState.phase == "FALANDO") AppState.phase = "PRONTO"
                        AppState.lastAudioEnd = System.currentTimeMillis(); AppState.update()
                    }
                } else if (item.pcm != null) {
                    if (current != item.id || pcm == null) {
                        pcm?.stop(); current = item.id
                        val latch = CountDownLatch(1); drained = latch
                        pcm = PcmPlayback(item.rate) { latch.countDown() }
                    }
                    AppState.audioBusy = true; AppState.phase = "FALANDO"; AppState.update()
                    pcm?.offer(item.pcm)
                }
            }
        } catch (_: InterruptedException) {
        } catch (e: Exception) { lastError = "stream: ${e.javaClass.simpleName}"; AppState.message("SYS", "Não foi possível reproduzir a voz remota. Confira o histórico e o volume do assistente.") }
        finally { pcm?.stop(); voice?.close(); AppState.audioBusy = false; AppState.update() }
    }
}
