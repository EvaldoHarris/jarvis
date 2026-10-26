package com.evaldoharris.jarvis

import android.Manifest
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.widget.*
import java.util.Locale

/** Central settings destination; navigation does not discard the main conversation. */
class SettingsActivity : FeatureActivity() {
    private lateinit var store: SecureStore
    private lateinit var status: TextView
    private lateinit var downloadStatus: TextView
    private lateinit var progress: ProgressBar
    private lateinit var download: Button
    private lateinit var cancelDownload: Button
    private lateinit var mode: Spinner
    private lateinit var key: EditText
    private lateinit var model: EditText
    private lateinit var address: EditText
    private lateinit var pin: EditText
    private lateinit var spoken: CheckBox
    private lateinit var liveAgent: CheckBox
    private lateinit var listening: Spinner
    private lateinit var target: Spinner
    private lateinit var shared: CheckBox
    private lateinit var sharedStatus: TextView
    private lateinit var voice: EditText
    private lateinit var voiceModel: EditText
    private var desiredRemote = false
    private var pairing = false
    private val update = object : Runnable {
        override fun run() {
            if (isFinishing || isDestroyed) return
            val percentage = (ModelDownload.bytes * 100 / ModelDownload.BYTES).toInt()
            progress.progress = percentage
            download.isEnabled = !ModelDownload.running
            cancelDownload.isEnabled = ModelDownload.running
            downloadStatus.text = when {
                ModelDownload.running -> "${ModelDownload.message} $percentage% • ${ModelDownload.bytes / 1048576} / ${ModelDownload.BYTES / 1048576} MB"
                ModelDownload.message.isNotBlank() -> ModelDownload.message
                LocalAi.installed(this@SettingsActivity) -> "Modelo local disponível neste celular."
                else -> "Modelo local ainda não instalado."
            }
            sharedStatus.text = DeviceSync.status
            ui.postDelayed(this, 400)
        }
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = SecureStore(this)
        line("‹  VOLTAR").apply { textSize = 13f; setTextColor(Ui.CYAN); setOnClickListener { finish() } }
        line("Configurações").apply { textSize = 28f; typeface = android.graphics.Typeface.create("sans-serif-light", android.graphics.Typeface.NORMAL) }
        status = line("As alterações são aplicadas ao tocar em SALVAR CONFIGURAÇÕES.")

        section("Ferramentas")
        button("NAVEGADOR") { startActivity(Intent(this, BrowserActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)) }
        button("CASA: CÂMERAS E LUZES") { startActivity(Intent(this, HomeActivity::class.java)) }
        button("MEMÓRIA, ARQUIVOS E TAREFAS") { startActivity(Intent(this, PersonalActivity::class.java)) }
        button("ACOMPANHAR TAREFAS DO PC") { startActivity(Intent(this, PcTasksActivity::class.java)) }

        section("Inteligência artificial")
        mode = select("Motor de IA", listOf("Automático", "Somente Gemini", "Somente IA local"), AiMode.values.indexOf(AiMode.normalize(store.get("ai_mode"))))
        line("Automático prioriza Gemini e usa o modelo local em caso de indisponibilidade. Local usa texto e acessibilidade; análise de imagens ainda requer Gemini.")
        key = input("Chave Gemini", store.get("gemini_key"), true)
        model = input("Modelo Gemini", store.get("gemini_model", "gemini-2.5-flash"))
        button("BUSCAR MODELOS GEMINI") {
            status.text = "Consultando modelos…"
            val apiKey = key.text.toString().trim()
            worker.execute {
                val result = runCatching { GeminiApi().models(apiKey) }
                ui.post { if (!isFinishing && !isDestroyed) result.onSuccess { models ->
                    if (models.isEmpty()) status.text = "Nenhum modelo disponível para esta chave."
                    else AlertDialog.Builder(this).setTitle("Modelos disponíveis").setItems(models.toTypedArray()) { _, i -> model.setText(models[i]) }.setNegativeButton("Cancelar", null).show()
                }.onFailure { status.text = it.message } }
            }
        }

        section("Modelo local")
        line("Qwen3 1.7B • aproximadamente 932 MB • texto • fonte LiteRT Community. O botão baixa o arquivo para este celular e verifica sua integridade. O desempenho precisa ser validado no aparelho. Mantenha o app aberto durante o download; se houver interrupção, toque novamente para tentar do início.")
        downloadStatus = line("")
        progress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply { max = 100; column.addView(this) }
        download = button("BAIXAR MODELO LOCAL") { ModelDownload.start(this) }
        cancelDownload = button("CANCELAR DOWNLOAD") { ModelDownload.cancel() }
        button("FONTE E LICENÇA DO MODELO") { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(ModelDownload.PAGE))) }

        section("Um só Jarvis — meus dispositivos")
        shared = CheckBox(this).apply { text = "Compartilhar memória, tarefas e contexto com meu PC principal"; setTextColor(Ui.TEXT); isChecked = store.get("shared_enabled", "true") == "true"; column.addView(this) }
        sharedStatus = line(DeviceSync.status)
        line("Usa o PC principal pela rede/VPN ou o canal direto protegido. O canal direto desta versão atende apenas à sincronização. Sem conexão, o celular continua independente e guarda as alterações para sincronizar depois. Arquivos, imagens, senhas e comandos não são copiados pela sincronização.")
        button("CANAL DIRETO PROTEGIDO — SEM VPN") { startActivity(Intent(this, DirectPairActivity::class.java)) }
        button("SINCRONIZAR AGORA") { DeviceSync.syncSoon() }
        button("REVISAR CONFLITOS DE SINCRONIZAÇÃO") {
            val conflicts = DeviceSync.conflicts()
            if (conflicts.length() == 0) { status.text = "Nenhum conflito pendente." }
            else {
                val names = (0 until conflicts.length()).map { conflicts.getJSONObject(it).getString("key") }.toTypedArray()
                AlertDialog.Builder(this).setTitle("Escolha o registro em conflito").setItems(names) { _, index ->
                    val row = conflicts.getJSONObject(index)
                    AlertDialog.Builder(this).setTitle(row.getString("key")).setMessage("Versão deste celular: " + row.opt("value").toString().take(1500) + "\n\nVersão do PC principal: " + row.opt("hub_value").toString().take(1500))
                        .setPositiveButton("Manter celular") { _, _ -> runCatching { DeviceSync.resolve(row.getString("kind"), row.getString("key"), true) }.onFailure { status.text = it.message } }
                        .setNeutralButton("Usar PC principal") { _, _ -> runCatching { DeviceSync.resolve(row.getString("kind"), row.getString("key"), false) }.onFailure { status.text = it.message } }
                        .setNegativeButton("Decidir depois", null).show()
                }.setNegativeButton("Fechar", null).show()
            }
        }

        section("Voz e ativação")
        listening = select("Como ativar o assistente", listOf("Dizer Jarvis", "Conversa contínua", "Somente botão FALAR"), listOf("wake", "continuous", "off").indexOf(store.get("voice_mode", "wake")).coerceAtLeast(0))
        spoken = CheckBox(this).apply { text = "Ler respostas em voz alta"; setTextColor(Ui.TEXT); isChecked = store.get("speak", "true") == "true"; column.addView(this) }
        liveAgent = CheckBox(this).apply { text = "Modo rápido (Gemini Live, igual ao PC)"; setTextColor(Ui.TEXT); isChecked = store.get("live_agent", "true") == "true"; column.addView(this) }
        line("Mantém uma conexão contínua com o Gemini: executa comandos e responde falando bem mais rápido. Usa o modelo de voz abaixo. Se falhar, o JARVIS volta ao modo normal automaticamente.")
        voice = input("Voz Gemini", store.get("voice_name", "Charon"))
        voiceModel = input("Modelo de voz Gemini", store.get("voice_model", "models/gemini-3.1-flash-live-preview"))
        line("A voz e o reconhecimento de fala são independentes do motor de IA e podem usar internet.")
        button("AJUSTAR RECONHECIMENTO DE JARVIS") { startActivity(Intent(this, WakeCalibrationActivity::class.java)) }

        section("Computador e acesso remoto")
        address = input("Endereço do PC (rede local ou VPN privada)", store.get("pc_url", "http://192.168.15.13:8000"))
        pin = input("Chave de pareamento do PC (8 caracteres)", "", true)
        button("PAREAR COM O PC") { pair() }
        target = select("Destino padrão dos pedidos de voz", listOf("Este Android", "Computador pareado"), if (store.get("voice_target_pc") == "true") 1 else 0)
        desiredRemote = store.get("remote_enabled") == "true"
        val remote = Switch(this).apply { text = "Permitir controle deste celular pelo PC"; setTextColor(Ui.TEXT); isChecked = desiredRemote; column.addView(this) }
        remote.setOnCheckedChangeListener { _, checked ->
            if (!checked) desiredRemote = false
            else if (store.get("pc_device_token").isBlank()) { status.text = "Pareie o computador antes de permitir controle."; remote.isChecked = false }
            else AlertDialog.Builder(this).setTitle("Permitir controle pelo PC?")
                .setMessage("O computador pareado poderá solicitar capturas de tela, abrir aplicativos, tocar e digitar enquanto esta opção estiver ligada e a acessibilidade estiver ativa.")
                .setPositiveButton("Permitir") { _, _ -> desiredRemote = true }
                .setNegativeButton("Cancelar") { _, _ -> remote.isChecked = false }
                .setOnCancelListener { remote.isChecked = false }.show()
        }
        line("Fora de casa, conecte PC e celular à mesma VPN privada e use o IP VPN do PC. Trocar o endereço remove o pareamento anterior.")

        section("Visão, permissões e integrações")
        line(getString(R.string.accessibility_description))
        button("CONFIGURAR ACESSIBILIDADE E CONTROLE") { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
        button("PERMISSÕES DO APLICATIVO") { startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName"))) }
        button("CONFIGURAR CÂMERAS, DVR E TUYA") { startActivity(Intent(this, HomeActivity::class.java)) }
        button("SALVAR CONFIGURAÇÕES") { save() }
        line("JARVIS ${packageManager.getPackageInfo(packageName, 0).versionName}")
    }
    private fun section(text: String) { line(text.uppercase(Locale.ROOT)).apply { textSize = 11f; letterSpacing = .22f; setTextColor(Ui.CYAN); setPadding(px(4), px(26), px(4), px(6)) } }
    private fun input(title: String, value: String, secret: Boolean = false): EditText { line(title); return field(column, title, value, secret).apply { isSingleLine = true } }
    private fun select(title: String, labels: List<String>, selected: Int): Spinner {
        line(title)
        return Spinner(this).apply {
            adapter = ArrayAdapter(this@SettingsActivity, android.R.layout.simple_spinner_dropdown_item, labels)
            background = Ui.pill(Ui.GLASS, Ui.LINE, px(12).toFloat()); setPadding(px(8), px(10), px(8), px(10)); setPopupBackgroundDrawable(Ui.pill(Ui.BG_TOP, Ui.LINE, px(12).toFloat()))
            setSelection(selected); column.addView(this)
        }
    }
    private fun save(): Boolean = try {
        val url = ServerAddress.normalize(address.text.toString())
        val previous = store.get("pc_url")
        val changedAddress = previous.isNotBlank() && previous != url
        if (changedAddress) {
            stopService(Intent(this, PhoneControlService::class.java)); store.put("pc_token", ""); store.put("pc_device_token", ""); desiredRemote = false
            store.put("shared_profile", "")
        }
        store.put("shared_enabled", shared.isChecked.toString())
        store.put("pc_url", url); store.put("ai_mode", AiMode.values[mode.selectedItemPosition])
        store.put("gemini_key", key.text.toString().trim()); store.put("gemini_model", GeminiModelPolicy.normalize(model.text.toString()))
        store.put("speak", spoken.isChecked.toString()); store.put("live_agent", liveAgent.isChecked.toString()); store.put("voice_name", voice.text.toString().trim().ifBlank { "Charon" })
        store.put("voice_model", voiceModel.text.toString().trim().ifBlank { "models/gemini-3.1-flash-live-preview" })
        store.put("voice_mode", listOf("wake", "continuous", "off")[listening.selectedItemPosition]); store.put("voice_target_pc", (target.selectedItemPosition == 1).toString())
        store.put("remote_enabled", desiredRemote.toString())
        if (!desiredRemote) stopService(Intent(this, PhoneControlService::class.java)) else startForegroundService(Intent(this, PhoneControlService::class.java))
        if (listening.selectedItemPosition == 2) stopService(Intent(this, WakeListeningService::class.java))
        else if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 14)
        else startForegroundService(Intent(this, WakeListeningService::class.java))
        status.text = if (changedAddress) "Salvo. Endereço alterado: pareie novamente o PC." else "Configurações salvas."
        DeviceSync.syncSoon(); AppState.update(); true
    } catch (e: Exception) { status.text = e.message; false }
    private fun pair() {
        if (pairing || !save()) return
        val code = pin.text.toString().trim().uppercase(Locale.ROOT)
        if (!Regex("[A-Z0-9]{8}").matches(code)) { status.text = "Informe os 8 caracteres exibidos pelo PC."; return }
        pairing = true; status.text = "Pareando…"
        worker.execute {
            val result = runCatching { PcClient(this).pair(code) }
            ui.post { pairing = false; if (!isFinishing && !isDestroyed) result.onSuccess { pin.setText(""); status.text = "PC pareado com sucesso." }.onFailure { status.text = it.message } }
        }
    }
    override fun onResume() { super.onResume(); ui.post(update) }
    override fun onPause() { ui.removeCallbacks(update); super.onPause() }
}
