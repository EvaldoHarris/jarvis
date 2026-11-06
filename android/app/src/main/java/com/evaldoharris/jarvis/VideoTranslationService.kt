package com.evaldoharris.jarvis

import android.app.*
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.*
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.*
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.nl.translate.Translation
import com.google.mlkit.nl.translate.TranslatorOptions
import org.vosk.Model
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

class VideoTranslationService : Service() {
    companion object {
        const val STOP = "translation.stop"
        const val AUDIO_ON = "translation.audio_on"
        const val AUDIO_OFF = "translation.audio_off"
        const val VOLUME = "translation.volume"
        private const val ID = 31
    }
    private val stopped = AtomicBoolean(false)
    private val captureWorker = Executors.newSingleThreadExecutor()
    private val translateWorker = Executors.newSingleThreadExecutor()
    private val pending = LinkedBlockingQueue<String>(64)
    private val main = Handler(Looper.getMainLooper())
    @Volatile private var record: AudioRecord? = null
    private var projection: MediaProjection? = null
    private var narrator: TranslationNarrator? = null
    private var started = false
    private var lastNotification = 0L

    override fun onBind(intent: Intent?) = null
    private fun notification(text: String): Notification {
        val open = PendingIntent.getActivity(this, 31, Intent(this, VideoTranslationActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val stop = PendingIntent.getService(this, 32, Intent(this, javaClass).setAction(STOP), PendingIntent.FLAG_IMMUTABLE)
        return Notification.Builder(this, "video_translation").setSmallIcon(R.drawable.ic_reactor)
            .setContentTitle("JARVIS — tradução de vídeo").setContentText(text.take(180)).setStyle(Notification.BigTextStyle().bigText(text.take(800)))
            .setVisibility(Notification.VISIBILITY_PRIVATE).setContentIntent(open).setOngoing(true)
            .addAction(Notification.Action.Builder(null, "Parar tradução", stop).build()).build()
    }
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            VOLUME -> { narrator?.setVolume(intent.getIntExtra("percent",100)); if(!started)stopSelf();return START_NOT_STICKY }
            STOP -> { stopSelf(); return START_NOT_STICKY }
            AUDIO_ON, AUDIO_OFF -> {
                VideoTranslationState.audio = intent.action == AUDIO_ON
                narrator?.setAudio(VideoTranslationState.audio); AppState.update()
                if (!started) stopSelf()
                return START_NOT_STICKY
            }
        }
        if (started) return START_NOT_STICKY
        val consent = if (Build.VERSION.SDK_INT >= 33) intent?.getParcelableExtra("consent", Intent::class.java) else {
            @Suppress("DEPRECATION") intent?.getParcelableExtra("consent")
        }
        if (consent == null || intent?.getIntExtra("result", 0) != Activity.RESULT_OK) { stopSelf(); return START_NOT_STICKY }
        try {
            check(checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) == android.content.pm.PackageManager.PERMISSION_GRANTED) { "Autorize a permissão de áudio antes de iniciar." }
            getSystemService(NotificationManager::class.java).createNotificationChannel(NotificationChannel("video_translation", "Tradução de vídeos", NotificationManager.IMPORTANCE_LOW))
            startForeground(ID, notification("Iniciando tradução local…"),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION or ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
            projection = getSystemService(MediaProjectionManager::class.java).getMediaProjection(Activity.RESULT_OK, consent)
            projection!!.registerCallback(object : MediaProjection.Callback() { override fun onStop() { stopSelf() } }, main)
            started = true
            VideoTranslationState.active = true; VideoTranslationState.audio = intent.getBooleanExtra("audio", true)
            VideoTranslationState.caption = ""; VideoTranslationState.update("Preparando reconhecimento local…")
            runCatching { startForegroundService(Intent(this,WakeListeningService::class.java)) }.onFailure {
                AppState.message("SYS","Abra o Jarvis e habilite a escuta para parar a tradução por voz; o botão Parar continua disponível.")
            }
            GeminiVoice.stop()
            narrator = TranslationNarrator(this) { error -> main.post {
                if (!stopped.get()) { VideoTranslationState.audio = false; narrator?.setAudio(false); VideoTranslationState.update(error) }
            } }.also { it.setAudio(VideoTranslationState.audio) }
            translateWorker.execute { translateLoop() }
            captureWorker.execute { captureLoop() }
        } catch (e: Exception) { fail(e) }
        return START_NOT_STICKY
    }
    private fun submit(text: String) {
        if (text.isBlank() || stopped.get()) return
        check(pending.offer(text)) { "A tradução não acompanhou o vídeo. Pause o vídeo antes de reiniciar; nenhum trecho será pulado silenciosamente." }
    }
    private fun captureLoop() {
        var model: Model? = null; var recognizer: TranslationRecognizer? = null; var audio: AudioRecord? = null
        try {
            check(TranslationModels.ready(this)) { "Prepare os modelos antes de iniciar a tradução." }
            model = Model(TranslationModels.path(this).absolutePath)
            recognizer = TranslationRecognizer(model)
            val currentProjection = projection ?: error("A captura foi encerrada")
            val config = AudioPlaybackCaptureConfiguration.Builder(currentProjection)
                .addMatchingUsage(AudioAttributes.USAGE_MEDIA).addMatchingUsage(AudioAttributes.USAGE_GAME)
                .addMatchingUsage(AudioAttributes.USAGE_UNKNOWN).excludeUid(Process.myUid()).build()
            val format = AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_16BIT).setSampleRate(16000)
                .setChannelMask(AudioFormat.CHANNEL_IN_MONO).build()
            val size = AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
            check(size > 0) { "O celular não oferece captura de áudio compatível" }
            if (checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != android.content.pm.PackageManager.PERMISSION_GRANTED)
                error("Permissão de áudio revogada. Autorize novamente antes de iniciar.")
            audio = AudioRecord.Builder().setAudioFormat(format).setBufferSizeInBytes(maxOf(size * 2, 64000))
                .setAudioPlaybackCaptureConfig(config).build()
            check(audio.state == AudioRecord.STATE_INITIALIZED) { "Não foi possível abrir a captura de áudio" }
            record = audio
            if (stopped.get()) return
            audio.startRecording()
            main.post { if (!stopped.get()) VideoTranslationState.update("Traduzindo inglês → português. Abra um vídeo em outro aplicativo.") }
            val bytes = ByteArray(3200)
            var anySound = false; var lastHint = SystemClock.elapsedRealtime()
            while (!stopped.get()) {
                val count = audio.read(bytes, 0, bytes.size, AudioRecord.READ_BLOCKING)
                if (stopped.get()) break
                check(count >= 0) { "Captura interrompida pelo Android (código $count)" }
                if (count == 0) continue
                var peak = 0
                for (i in 0 until count - 1 step 2) {
                    val value = ((bytes[i].toInt() and 255) or (bytes[i + 1].toInt() shl 8)).toShort().toInt()
                    peak = maxOf(peak, kotlin.math.abs(value))
                }
                anySound = anySound || peak > 100
                recognizer.accept(bytes,count)?.let(::submit)
                val now = SystemClock.elapsedRealtime()
                if (now - lastHint > 12000) {
                    if (!anySound) main.post { if (!stopped.get()) VideoTranslationState.update("Sem áudio capturável. Confira se o vídeo está tocando; alguns apps bloqueiam captura.") }
                    anySound = false; lastHint = now
                }
            }
        } catch (e: Exception) { if (!stopped.get()) fail(e) }
        finally {
            record = null
            runCatching { audio?.stop() }; audio?.release(); recognizer?.close(); model?.close()
        }
    }
    private fun translateLoop() {
        val translator = Translation.getClient(TranslatorOptions.Builder().setSourceLanguage("en").setTargetLanguage("pt").build())
        try {
            while (!stopped.get()) {
                val item = pending.poll(200, TimeUnit.MILLISECONDS) ?: continue
                val text = Tasks.await(translator.translate(item), 15, TimeUnit.SECONDS)
                if (stopped.get() || text.isBlank()) continue
                main.post {
                    if (!stopped.get()) {
                        VideoTranslationState.caption = text
                        VideoTranslationState.update("Tradução local ativa — inglês → português")
                        val now = SystemClock.elapsedRealtime()
                        if (now - lastNotification > 1000) {
                            getSystemService(NotificationManager::class.java).notify(ID, notification(text)); lastNotification = now
                        }
                        narrator?.offer(text)
                    }
                }
            }
        } catch (_: InterruptedException) { /* stopped */ }
        catch (e: Exception) { if (!stopped.get()) fail(e) }
        finally { translator.close() }
    }
    private fun fail(e: Exception) { main.post {
        if (!stopped.get()) { VideoTranslationState.update("Tradução interrompida: ${e.message?.take(220)}"); stopSelf() }
    } }
    override fun onDestroy() {
        stopped.set(true); pending.clear(); runCatching { record?.stop() }; narrator?.close(); narrator = null
        projection?.stop(); projection = null
        captureWorker.shutdownNow(); translateWorker.shutdownNow()
        VideoTranslationState.active = false
        VideoTranslationState.pauseNarrationUntil=0;VideoTranslationState.speaking=false;VideoTranslationState.spokenText="";VideoTranslationState.lastNarrationEnd=0
        if (!VideoTranslationState.status.startsWith("Tradução interrompida")) VideoTranslationState.status = "Tradução parada"
        AppState.lastAudioEnd = System.currentTimeMillis(); AppState.update()
        stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }
}
