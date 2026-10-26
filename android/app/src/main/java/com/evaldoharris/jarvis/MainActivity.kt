package com.evaldoharris.jarvis

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.provider.Settings
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.text.InputType
import android.util.Base64
import android.view.Gravity
import android.view.View
import android.widget.*
import androidx.core.content.FileProvider
import java.io.File
import java.util.Locale
import java.util.concurrent.Executors

class MainActivity : Activity() {
    private val background = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private lateinit var store: SecureStore
    private lateinit var status: TextView
    private lateinit var transcript: TextView
    private lateinit var input: EditText
    private lateinit var imageLabel: TextView
    private lateinit var conversation: LinearLayout
    private lateinit var conversationScroll: ScrollView
    private var renderedMessages = -1
    private lateinit var wakeBanner: TextView
    private var speech: SpeechRecognizer? = null
    private var voiceActive = false
    private var voiceRetried = false
    private var voiceGeneration = 0
    private var voiceRequest = 0
    private var pendingImage: String? = null
    private var targetPcOnce: Boolean? = null
    private var cameraFile: File? = null
    private val refresh: () -> Unit = { renderState() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = SecureStore(this)
        DeviceSync.start(applicationContext)
        if (AppState.assistant == null) AppState.assistant = JarvisAssistant(applicationContext)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; background = Ui.backdrop() }
        root.setOnApplyWindowInsetsListener { view, insets ->
            val bars = insets.getInsets(android.view.WindowInsets.Type.systemBars() or android.view.WindowInsets.Type.ime())
            view.setPadding(dp(16) + bars.left, dp(6) + bars.top, dp(16) + bars.right, dp(10) + bars.bottom); insets
        }
        // Barra superior: nome, estado da conexão e configurações
        val header = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
        val titleBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        titleBox.addView(TextView(this).apply { text = "J.A.R.V.I.S"; textSize = 17f; letterSpacing = .25f; setTextColor(Ui.CYAN); typeface = Typeface.create("sans-serif-light", Typeface.BOLD) })
        status = TextView(this).apply { textSize = 10f; letterSpacing = .12f; setTextColor(Ui.MUTED); typeface = Typeface.MONOSPACE }
        titleBox.addView(status)
        header.addView(titleBox, LinearLayout.LayoutParams(0, -2, 1f))
        header.addView(Ui.iconButton(this, "⚙", "Configurações") { settings() }, LinearLayout.LayoutParams(dp(44), dp(44)))
        root.addView(header, LinearLayout.LayoutParams(-1, dp(52)))
        // Rosto: sempre visível, fora da área que rola
        root.addView(ReactorView(this).apply { id = R.id.reactor }, LinearLayout.LayoutParams(-1, (resources.displayMetrics.heightPixels * .30f).toInt().coerceIn(dp(170), dp(300))))
        wakeBanner = TextView(this).apply {
            id = R.id.wake_status; gravity = Gravity.CENTER; textSize = 11f; letterSpacing = .14f; typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
            setPadding(dp(16), dp(7), dp(16), dp(7)); background = Ui.pill(Ui.GLASS, Ui.LINE)
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        }
        root.addView(wakeBanner, LinearLayout.LayoutParams(-2, -2).apply { gravity = Gravity.CENTER_HORIZONTAL; bottomMargin = dp(8) })
        // Conversa
        val scroll = ScrollView(this).apply { id = R.id.conversation_scroll; isFillViewport = true; isVerticalScrollBarEnabled = false; isVerticalFadingEdgeEnabled = true; setFadingEdgeLength(dp(24)) }
        conversation = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(0, dp(8), 0, dp(8)) }
        scroll.addView(conversation); root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        conversationScroll = scroll
        transcript = TextView(this)
        imageLabel = TextView(this).apply { textSize = 11f; setTextColor(Ui.GREEN); visibility = View.GONE; setPadding(dp(14), 0, dp(14), dp(6)) }
        root.addView(imageLabel)
        // Barra de entrada
        val bar = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL; background = Ui.pill(Ui.GLASS, Ui.LINE); setPadding(dp(4), dp(4), dp(4), dp(4)) }
        bar.addView(Ui.iconButton(this, "+", "Anexar imagem") { attach() }, LinearLayout.LayoutParams(dp(42), dp(42)))
        input = EditText(this).apply {
            hint = "Fale ou digite…"; setHintTextColor(Ui.MUTED); setTextColor(Ui.TEXT); maxLines = 4; textSize = 15f
            background = null; setPadding(dp(8), dp(8), dp(8), dp(8)); inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES or InputType.TYPE_TEXT_FLAG_MULTI_LINE
        }
        bar.addView(input, LinearLayout.LayoutParams(0, -2, 1f))
        bar.addView(Ui.iconButton(this, "■", "Parar") { stopAll() }, LinearLayout.LayoutParams(dp(42), dp(42)))
        bar.addView(Ui.iconButton(this, "➤", "Enviar") { send() }, LinearLayout.LayoutParams(dp(42), dp(42)))
        bar.addView(Ui.iconButton(this, "🎙", "Falar", filled = true) { listen() }, LinearLayout.LayoutParams(dp(48), dp(48)).apply { leftMargin = dp(4) })
        root.addView(bar, LinearLayout.LayoutParams(-1, -2))
        setContentView(root)
        consumeImage(intent)
        TaskReminders.restore(this)
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 12)
    }

    override fun onResume() {
        super.onResume(); AppState.listeners.add(refresh); AppState.mainVisible = true; AppState.update(); renderState(); AppState.assistant?.warmLive()
        if (store.get("remote_enabled") == "true") startRemote()
        startHandsFree()
    }
    override fun onPause() { AppState.listeners.remove(refresh); AppState.mainVisible = false; AppState.update(); super.onPause() }
    override fun onDestroy() { voiceActive = false; AppState.manualListening = false; voiceGeneration++; speech?.destroy(); main.removeCallbacksAndMessages(null); background.shutdownNow(); super.onDestroy() }
    override fun onNewIntent(intent: Intent) { super.onNewIntent(intent); setIntent(intent); consumeImage(intent) }
    private fun consumeImage(intent: Intent) {
        val path = intent.getStringExtra("screen_image") ?: return
        val file = File(path)
        if (file.canonicalPath != File(cacheDir, "observed_screen.jpg").canonicalPath || !file.exists()) return
        pendingImage = Base64.encodeToString(file.readBytes(), Base64.NO_WRAP); file.delete()
        showImage("Tela capturada. Digite o que deseja analisar e toque ➤."); targetPcOnce = false
        intent.removeExtra("screen_image")
    }
    private fun renderState() {
        val ready = AppState.readyForCommand()
        val banner = when {
            AppState.assistantBusy -> "PENSANDO…"
            AppState.audioBusy -> "RESPONDENDO"
            AppState.expectedPhoneReply.isNotEmpty() -> "AGUARDANDO O PC"
            ready -> "●  PODE FALAR — ESTOU OUVINDO"
            AppState.manualListening -> "●  PODE FALAR"
            store.get("voice_mode", "wake") == "off" -> "TOQUE NO MICROFONE PARA FALAR"
            AppState.phase == "PREPARANDO ESCUTA" -> "PREPARANDO O MICROFONE…"
            !AppState.wakeRunning -> "ABRA A ESCUTA PARA DIZER JARVIS"
            store.get("voice_mode") == "continuous" -> "ESCUTA CONTÍNUA — PODE FALAR"
            else -> "DIGA JARVIS PARA COMEÇAR"
        }
        if (wakeBanner.text.toString() != banner) wakeBanner.text = banner
        val live = ready || AppState.manualListening
        wakeBanner.setTextColor(if (live) Ui.GREEN else Ui.TEXT)
        wakeBanner.background = Ui.pill(Ui.GLASS, if (live) Ui.GREEN else Ui.LINE)
        val pc = if (store.get("voice_target_pc") == "true") "DESTINO: PC" else "DESTINO: ANDROID"
        status.text = "${AppState.connection.uppercase(Locale.ROOT)}  •  $pc"
        transcript.text = AppState.transcript()
        renderMessages()
    }
    private fun renderMessages() {
        val items = synchronized(AppState.messages) { AppState.messages.toList() }
        val signature = items.size * 31 + (items.lastOrNull()?.hashCode() ?: 0)
        if (signature == renderedMessages && conversation.childCount > 0) return
        renderedMessages = signature
        conversation.removeAllViews()
        if (items.isEmpty()) {
            conversation.addView(TextView(this).apply {
                text = "Olá. Estou pronta para ajudar.\nConfigure a chave de IA em ⚙ para começar."
                gravity = Gravity.CENTER; textSize = 13f; setTextColor(Ui.MUTED); setPadding(dp(16), dp(24), dp(16), dp(24))
            })
            return
        }
        items.forEach { raw ->
            val split = raw.indexOf(": ")
            val who = if (split > 0) raw.substring(0, split) else ""
            val body = if (split > 0) raw.substring(split + 2) else raw
            conversation.addView(Ui.bubble(this, who, body))
        }
        conversationScroll.post { conversationScroll.fullScroll(View.FOCUS_DOWN) }
    }
    private fun showImage(text: String) { imageLabel.text = "◉  $text"; imageLabel.visibility = View.VISIBLE }
    private fun attach() {
        AlertDialog.Builder(this).setTitle("Anexar")
            .setItems(arrayOf("Tirar foto com a câmera", "Ver a tela de outro aplicativo")) { _, i -> if (i == 0) camera() else observeScreen() }.show()
    }
    private fun stopAll() {
        AppState.assistant?.cancel(); stopVoice(); GeminiVoice.stop(); AppState.stopRemoteSpeech?.invoke()
        store.put("voice_mode", "off"); stopService(Intent(this, WakeListeningService::class.java)); AppState.phase = "PRONTO"; AppState.update()
    }
    private fun startRemote() {
        store.put("remote_enabled", "true")
        try { startForegroundService(Intent(this, PhoneControlService::class.java)) }
        catch (_: Exception) { AppState.message("SYS", "Android não permitiu iniciar a conexão em segundo plano. Abra o app e tente novamente.") }
    }
    private fun send() {
        val text = input.text.toString().trim().ifEmpty { if (pendingImage != null) "Descreva esta imagem." else "" }
        if (text.isEmpty()) return
        GeminiVoice.stop(); stopVoice()
        val image = pendingImage; pendingImage = null; imageLabel.text = ""; imageLabel.visibility = View.GONE; input.setText("")
        val toPc = targetPcOnce ?: (store.get("voice_target_pc") == "true"); targetPcOnce = null
        AppState.assistant?.ask(text, image, toPc) { answer ->
            GeminiVoice.speak(applicationContext, answer)
        }
    }
    private fun startHandsFree() {
        if (store.get("voice_mode", "wake") == "off" || checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) return
        try { startForegroundService(Intent(this, WakeListeningService::class.java)) }
        catch (_: Exception) { AppState.message("SYS", "Android não permitiu iniciar a escuta. Abra o app e habilite o microfone.") }
    }
    private fun listen() {
        store.put("speak", "true")
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) { requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 10); return }
        if (!SpeechRecognizer.isRecognitionAvailable(this)) { AppState.message("SYS", "Instale ou habilite um serviço de reconhecimento de voz no Android."); return }
        if (voiceActive) { speech?.stopListening(); return }
        GeminiVoice.stop(); AppState.stopRemoteSpeech?.invoke(); voiceRetried = false; voiceRequest++
        AppState.manualListening = true
        main.postDelayed({ startRecognition() }, if (AppState.wakeRunning) 400 else 0)
    }
    private fun stopVoice() {
        voiceRequest++
        AppState.manualListening = false
        if (!voiceActive) return
        voiceActive = false
        speech?.cancel()
    }
    private fun startRecognition() {
        if (isFinishing || isDestroyed) return
        voiceActive = true
        AppState.manualListening = true
        if (speech == null) {
            val generation = ++voiceGeneration
            speech = SpeechRecognizer.createSpeechRecognizer(this).apply {
            setRecognitionListener(object : RecognitionListener {
                private fun current() = generation == voiceGeneration && voiceActive
                override fun onReadyForSpeech(params: Bundle?) { if (current()) { AppState.phase = "OUVINDO"; AppState.update() } }
                override fun onResults(results: Bundle?) {
                    if (!current()) return
                    voiceActive = false
                    val phrase = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty()
                    AppState.manualListening = false
                    input.setText(phrase); AppState.phase = "PRONTO"; AppState.update()
                    val request = voiceRequest
                    if (phrase.isNotEmpty()) main.post { if (voiceRequest == request) send() }
                }
                override fun onError(error: Int) {
                    if (!current()) return
                    voiceActive = false
                    android.util.Log.w("JarvisVoice", "recognition_error=$error")
                    if (error == 11) {
                        speech?.destroy(); speech = null; voiceGeneration++
                        if (VoiceInputPolicy.retryDisconnected(error, voiceRetried)) {
                            voiceRetried = true; AppState.phase = "RECONECTANDO MICROFONE"; AppState.update()
                            val retryRequest = voiceRequest
                            main.postDelayed({ if (voiceRequest == retryRequest) startRecognition() }, 800)
                            return
                        }
                        try {
                            AppState.phase = "OUVINDO"; AppState.update()
                            startActivityForResult(voiceIntent(), 30)
                            return
                        } catch (_: Exception) { }
                    }
                    AppState.manualListening = false
                    AppState.phase = "PRONTO"; AppState.update()
                    AppState.message("SYS", VoiceInputPolicy.message(error))
                }
                override fun onBeginningOfSpeech() = Unit
                override fun onRmsChanged(rmsdB: Float) = Unit
                override fun onBufferReceived(buffer: ByteArray?) = Unit
                override fun onEndOfSpeech() { if (current()) { AppState.phase = "PENSANDO"; AppState.update() } }
                override fun onPartialResults(partialResults: Bundle?) = Unit
                override fun onEvent(eventType: Int, params: Bundle?) = Unit
            })
            }
        }
        try { speech?.startListening(voiceIntent()) }
        catch (_: Exception) { voiceActive = false; AppState.phase = "PRONTO"; AppState.message("SYS", "Não foi possível iniciar o microfone. Confira o serviço de voz do Android.") }
    }
    private fun voiceIntent() = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
        .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR").putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        .putExtra(RecognizerIntent.EXTRA_PROMPT, "Fale com o JARVIS")
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 14) { if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) startHandsFree(); return }
        if (requestCode == 10) {
            if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) listen()
            else AppState.message("SYS", VoiceInputPolicy.message(9))
        }
    }
    private fun observeScreen() {
        if (JarvisAccessibilityService.current == null) { explainAccessibility(); return }
        AlertDialog.Builder(this).setTitle("Observar outro aplicativo")
            .setMessage("Abra o aplicativo desejado e toque no pequeno reator flutuante na lateral. Ele captura a tela antes de abrir o JARVIS. Você escolhe o pedido e confirma o envio à IA.")
            .setPositiveButton("Entendi") { _, _ -> moveTaskToBack(true) }.show()
    }
    private fun camera() {
        val directory = File(cacheDir, "camera").apply { mkdirs() }
        cameraFile = File(directory, "capture.jpg")
        val uri = FileProvider.getUriForFile(this, "$packageName.files", cameraFile!!)
        try { startActivityForResult(Intent(MediaStore.ACTION_IMAGE_CAPTURE).putExtra(MediaStore.EXTRA_OUTPUT, uri).addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION or Intent.FLAG_GRANT_READ_URI_PERMISSION), 20) }
        catch (_: Exception) { AppState.message("SYS", "Nenhum aplicativo de câmera disponível.") }
    }
    @Deprecated("Platform activity result used to avoid unnecessary UI dependencies")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == 30) {
            AppState.manualListening = false
            AppState.phase = "PRONTO"; AppState.update()
            val phrase = data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull().orEmpty()
            if (resultCode == RESULT_OK && phrase.isNotBlank()) { input.setText(phrase); send() }
            return
        }
        if (requestCode == 20 && resultCode == RESULT_OK) {
            val file = cameraFile ?: File(cacheDir, "camera/capture.jpg")
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }; BitmapFactory.decodeFile(file.path, bounds)
            val options = BitmapFactory.Options().apply { inSampleSize = (maxOf(bounds.outWidth, bounds.outHeight) / 1600).coerceAtLeast(1) }
            val bitmap = BitmapFactory.decodeFile(file.path, options)
            if (bitmap != null) { pendingImage = PhoneTools.encode(bitmap); bitmap.recycle(); file.delete(); targetPcOnce = false; showImage("Foto pronta para análise. Toque ➤.") }
        }
    }
    private fun explainAccessibility() {
        AlertDialog.Builder(this).setTitle("Visão e controle do Android")
            .setMessage(getString(R.string.accessibility_description))
            .setPositiveButton("Abrir acessibilidade") { _, _ -> startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }.setNegativeButton("Cancelar", null).show()
    }
    private fun settings() { startActivity(Intent(this, SettingsActivity::class.java)) }
    private fun dp(value: Int) = (resources.displayMetrics.density * value).toInt()
}
