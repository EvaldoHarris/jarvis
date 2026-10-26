package com.evaldoharris.jarvis

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.media.AudioFormat
import android.os.Bundle
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer

/** Explicit microphone foreground service; never starts from boot or a remote command. */
class WakeListeningService : Service() {
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var store: SecureStore
    private var recognizer: SpeechRecognizer? = null
    private var microphone: ContinuousMicrophone? = null
    private var listening = false
    private var stopping = false
    private var nextListen = 0L
    private var generation = 0
    private var disconnects = 0
    private var recognitionReady = false
    private var segmentedEstablished = false
    private var needsCue = false
    private var cue: WakeCue? = null
    private val phrase = WakePhrase()
    private var spotter: WakeSpotter? = null
    // Frase que o Google entendeu sem o nome; se o detector ouvir "Jarvis" logo em seguida, ela vira o pedido.
    private var pendingText = ""
    private var pendingAt = 0L
    private val tick = object : Runnable {
        override fun run() {
            if (stopping) return
            val mode = store.get("voice_mode", "wake")
            if (mode == "off") { stopSelf(); return }
            if(mode!="wake"){phrase.reset();needsCue=false;AppState.wakeReadyUntil=0}
            if (AppState.expectedPhoneReply.isNotEmpty() && AppState.phoneReplyDeadline > 0 && System.currentTimeMillis() > AppState.phoneReplyDeadline) {
                GeminiVoice.finishPc(AppState.expectedPhoneReply); AppState.expectedPhoneReply = ""
                AppState.message("SYS", "O canal de resposta do PC ficou sem atividade; a escuta foi liberada.")
            }
            val busy = AppState.assistantBusy || AppState.audioBusy || AppState.manualListening || AppState.expectedPhoneReply.isNotEmpty()
            if (AppState.manualListening && listening) cancelListening()
            if (listening && !busy) updateListeningPhase()
            if (!busy && !listening && System.currentTimeMillis() >= maxOf(nextListen, AppState.lastAudioEnd + 650)) startListening()
            handler.postDelayed(this, 250)
        }
    }
    override fun onCreate() {
        super.onCreate(); store = SecureStore(this)
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) { stopSelf(); return }
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("jarvis_microphone", "Escuta do JARVIS", NotificationManager.IMPORTANCE_LOW))
        val stop = PendingIntent.getService(this, 12, Intent(this, javaClass).setAction("stop"), PendingIntent.FLAG_IMMUTABLE)
        val open = PendingIntent.getActivity(this, 13, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        startForeground(2, Notification.Builder(this, "jarvis_microphone").setSmallIcon(R.drawable.ic_reactor)
            .setContentTitle("JARVIS — microfone ativo").setContentText("Diga Jarvis e seu pedido. Toque em Parar escuta para desligar.")
            .setOngoing(true).setContentIntent(open).addAction(Notification.Action.Builder(null, "Parar escuta", stop).build()).build())
        AppState.wakeRunning = true
        WakeSpotter.preload(this)
        cue = WakeCue(this)
    }
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "stop") { store.put("voice_mode", "off"); stopSelf(); return START_NOT_STICKY }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) { stopSelf(); return START_NOT_STICKY }
        if (!SpeechRecognizer.isRecognitionAvailable(this)) { AppState.message("SYS", "Nenhum serviço de reconhecimento de voz disponível."); stopSelf(); return START_NOT_STICKY }
        if (AppState.assistant == null) AppState.assistant = JarvisAssistant(applicationContext)
        phrase.configureAlias(store.get("wake_alias"))
        handler.removeCallbacks(tick); handler.post(tick)
        return START_NOT_STICKY
    }
    private fun cancelListening() {
        recognitionReady = false; AppState.wakeReadyUntil = 0; needsCue = false; phrase.reset()
        listening = false; recognizer?.cancel(); microphone?.close(); microphone = null
        nextListen = System.currentTimeMillis() + 700
    }
    private fun busy() = AppState.assistantBusy || AppState.audioBusy || AppState.manualListening || AppState.expectedPhoneReply.isNotEmpty() || System.currentTimeMillis() < AppState.lastAudioEnd + 650
    private fun updateListeningPhase() {
        val now=System.currentTimeMillis()
        if(needsCue && recognitionReady && phrase.armed(now)){
            needsCue=false;phrase.arm(now);cue?.play()
        }
        AppState.wakeReadyUntil=if(recognitionReady&&phrase.armed(now))phrase.deadline()else 0
        val phase = if(!recognitionReady) "PREPARANDO ESCUTA" else if (phrase.armed(now)) "PODE FALAR" else if (store.get("voice_mode", "wake") == "wake") "AGUARDANDO JARVIS" else "OUVINDO"
        if (AppState.phase != phase) { AppState.phase = phase; AppState.update() }
    }
    private fun result(results: Bundle?) {
        if (busy()) return
        val candidates=results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION).orEmpty()
        android.util.Log.d("JarvisWakeText", "heard=${candidates.take(5)} scores=${results?.getFloatArray(SpeechRecognizer.CONFIDENCE_SCORES)?.take(5)}")
        val text = if(phrase.expectingFollowup(System.currentTimeMillis()))candidates.firstOrNull().orEmpty() else
            WakeWords.choose(candidates,results?.getFloatArray(SpeechRecognizer.CONFIDENCE_SCORES),store.get("wake_alias"))
        val now=System.currentTimeMillis();val wasArmed=phrase.armed(now)
        val command = phrase.command(text, store.get("voice_mode", "wake"), now)
        if (command == null && text.isNotBlank() && !phrase.armed(now)) { pendingText = text; pendingAt = now }
        if (command != null) {
            pendingText = ""
            needsCue=false;AppState.wakeReadyUntil=0
            store.put("speak", "true")
            AppState.assistant?.ask(command, targetPc = store.get("voice_target_pc") == "true") { GeminiVoice.speak(applicationContext, it) }
        } else {
            if(!wasArmed&&phrase.armed(now)){needsCue=true;AppState.assistant?.warmLive()}
            updateListeningPhase()
        }
    }
    /** O detector offline ouviu o nome. */
    private fun spotted(word: String) {
        if (stopping || busy() || store.get("voice_mode", "wake") != "wake") return
        val now = System.currentTimeMillis()
        android.util.Log.d("JarvisWake", "spotter_wake=$word")
        // O Google já entregou a frase inteira (sem reconhecer o nome): executa como pedido.
        val recent = if (now - pendingAt < 2500) WakeWords.stripLeading(pendingText) else ""
        pendingText = ""
        if (recent.isNotBlank()) {
            needsCue = false; AppState.wakeReadyUntil = 0; phrase.reset()
            store.put("speak", "true")
            AppState.assistant?.ask(recent, targetPc = store.get("voice_target_pc") == "true") { GeminiVoice.speak(applicationContext, it) }
            return
        }
        if (!phrase.armed(now)) { phrase.arm(now); needsCue = true }
        AppState.assistant?.warmLive()
        updateListeningPhase()
    }
    private fun startListening() {
        AppState.phase="PREPARANDO ESCUTA";AppState.update()
        if (recognizer == null) {
            val current = ++generation
            recognizer = SpeechRecognizer.createSpeechRecognizer(this).apply {
                setRecognitionListener(object : RecognitionListener {
                    private fun valid() = current == generation && listening && !stopping
                    override fun onReadyForSpeech(params: Bundle?) { if (valid()) { recognitionReady=true;updateListeningPhase() } }
                    override fun onSegmentResults(segmentResults: Bundle) {
                        if (!valid()) return
                        android.util.Log.d("JarvisWake", "segment_received")
                        segmentedEstablished=true;recognitionReady=true
                        disconnects = 0; result(segmentResults)
                    }
                    override fun onEndOfSegmentedSession() {
                        if (!valid()) return
                        recognitionReady=false;AppState.wakeReadyUntil=0
                        listening = false; microphone?.close(); microphone = null
                        nextListen = System.currentTimeMillis() + 1500
                        updateListeningPhase()
                    }
                    override fun onResults(results: Bundle?) {
                        if (!valid()) return
                        recognitionReady=false;AppState.wakeReadyUntil=0
                        listening = false; microphone?.close(); microphone = null
                        disconnects = 0; nextListen = System.currentTimeMillis() + 1500
                        result(results)
                    }
                    override fun onError(error: Int) {
                        if (!valid()) return
                        android.util.Log.w("JarvisWake", "recognition_error=$error")
                        recognitionReady=false;AppState.wakeReadyUntil=0;needsCue=false;phrase.reset()
                        listening = false; microphone?.close(); microphone = null
                        nextListen = System.currentTimeMillis() + when (error) { 1,2,4 -> 6000; 8,11 -> 2000; else -> 700 }
                        if (error == 11) { recognizer?.destroy(); recognizer = null; generation++; disconnects++ }
                        if (error in listOf(9,12,13) || disconnects >= 4) { store.put("voice_mode", "off"); AppState.message("SYS", VoiceInputPolicy.message(error)); stopSelf() }
                        else updateListeningPhase()
                    }
                    override fun onBeginningOfSpeech() = Unit
                    override fun onRmsChanged(rmsdB: Float) = Unit
                    override fun onBufferReceived(buffer: ByteArray?) = Unit
                    override fun onEndOfSpeech() = Unit
                    override fun onPartialResults(partialResults: Bundle?) {
                        if(!valid()||busy()||!segmentedEstablished||!recognitionReady)return
                        val text=partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty()
                        if(text.isNotBlank())android.util.Log.d("JarvisWakeText","partial=$text")
                        if(phrase.preview(text,store.get("voice_mode","wake"),System.currentTimeMillis())){needsCue=true;AppState.assistant?.warmLive();updateListeningPhase()}
                    }
                    override fun onEvent(eventType: Int, params: Bundle?) = Unit
                })
            }
        }
        listening = true
        try {
            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR").putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 5)
                .putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS,true)
            if (Build.VERSION.SDK_INT >= 33) {
                intent.putStringArrayListExtra(RecognizerIntent.EXTRA_BIASING_STRINGS,WakeWords.bias(store.get("wake_alias")))
                spotter?.close()
                spotter = if (store.get("voice_mode", "wake") == "wake") WakeSpotter { word -> handler.post { spotted(word) } } else null
                val capture = ContinuousMicrophone({ busy() }, spotter?.let { s -> { buffer: ByteArray, count: Int -> s.feed(buffer, count) } })
                microphone = capture
                intent.putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE, capture.source)
                    .putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_CHANNEL_COUNT, 1)
                    .putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_ENCODING, AudioFormat.ENCODING_PCM_16BIT)
                    .putExtra(RecognizerIntent.EXTRA_AUDIO_SOURCE_SAMPLING_RATE, 16000)
                    .putExtra(RecognizerIntent.EXTRA_SEGMENTED_SESSION, RecognizerIntent.EXTRA_AUDIO_SOURCE)
                recognizer?.startListening(intent)
                capture.start { handler.post { if (!stopping) { cancelListening(); nextListen = System.currentTimeMillis() + 6000 } } }
                android.util.Log.d("JarvisWake", "continuous_capture_started")
            } else recognizer?.startListening(intent)
        } catch (_: Exception) { cancelListening(); nextListen = System.currentTimeMillis() + 4000 }
    }
    override fun onDestroy() {
        stopping = true; microphone?.close(); microphone = null; generation++; handler.removeCallbacksAndMessages(null); recognizer?.destroy()
        recognitionReady=false;AppState.wakeReadyUntil=0;needsCue=false;cue?.close();cue=null;spotter?.close();spotter=null
        AppState.wakeRunning = false; if (!AppState.audioBusy && !AppState.assistantBusy) AppState.phase = "PRONTO"
        AppState.update(); super.onDestroy()
    }
    override fun onBind(intent: Intent?): IBinder? = null
}
