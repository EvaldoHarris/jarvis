package com.evaldoharris.jarvis

import android.content.Intent
import android.os.Bundle
import android.widget.EditText
import android.widget.TextView
import com.google.zxing.integration.android.IntentIntegrator


class DirectPairActivity : FeatureActivity() {
    private lateinit var ticket: EditText
    private lateinit var status: TextView
    private var pairing = false
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        line("CONEXÃO DIRETA PROTEGIDA")
        line("Na mesma rede do PC, abra o pareamento direto dele. Escaneie o QR ou importe o convite .jarvis. O convite expira em 10 minutos; a chave privada do celular fica no Android Keystore.")
        ticket = field(column, "Convite jarvis-direct:", "").apply {
            maxLines = 4; inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
            importantForAutofill = android.view.View.IMPORTANT_FOR_AUTOFILL_NO; isSaveEnabled = false
        }
        status = line("Esta primeira versão protege a sincronização. Controle remoto por este canal ainda não está habilitado.")
        button("ESCANEAR QR DO PC") {
            IntentIntegrator(this).apply {
                setCaptureActivity(DirectQrScannerActivity::class.java)
                setDesiredBarcodeFormats(IntentIntegrator.QR_CODE)
                setPrompt("Aponte para o QR Code do Jarvis no PC")
                setBeepEnabled(true)
                setBarcodeImageEnabled(false)
                setOrientationLocked(false)
            }.initiateScan()
        }
        button("IMPORTAR CONVITE .jarvis") { startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*"), 81) }
        button("PAREAR CANAL PROTEGIDO") { pair() }
        button("CONFIGURAR ENDEREÇO LOCAL HTTPS") {
            val store = SecureStore(this)
            runCatching {
                val cfg = org.json.JSONObject(store.get("direct_config"))
                val input = field(android.widget.LinearLayout(this).apply { orientation = android.widget.LinearLayout.VERTICAL }, "https://IP-LOCAL-DO-PC:9443", cfg.optString("local_url", cfg.getString("url")))
                android.app.AlertDialog.Builder(this).setTitle("Endereço do PC no Wi-Fi").setView(input.parent as android.view.View)
                    .setMessage("Informe o IP local do PC. O endereço externo será preservado e o certificado continuará sendo verificado.")
                    .setPositiveButton("Salvar") { _, _ -> runCatching {
                        val url = ServerAddress.normalize(input.text.toString()); require(url.startsWith("https://"))
                        cfg.put("local_url", url); store.put("direct_config", cfg.toString())
                        status.text = "Endereço local salvo; endereço externo preservado."; DeviceSync.syncSoon()
                    }.onFailure { status.text = it.message } }.setNegativeButton("Cancelar", null).show()
            }.onFailure { status.text = "Pareie o canal primeiro." }
        }
        button("USAR ENDEREÇO EXTERNO HTTPS") {
            val store = SecureStore(this)
            runCatching {
                val cfg = org.json.JSONObject(store.get("direct_config"))
                val input = field(android.widget.LinearLayout(this).apply { orientation = android.widget.LinearLayout.VERTICAL }, "https://IP-PÚBLICO-DO-PC:9443", cfg.optString("external_url", ""))
                android.app.AlertDialog.Builder(this).setTitle("Endereço direto do mesmo PC").setView(input.parent as android.view.View).setMessage("O certificado do PC deve conter este IP. Não altera roteador nem firewall.")
                    .setPositiveButton("Salvar") { _, _ -> runCatching {
                        val url = ServerAddress.normalize(input.text.toString()); require(url.startsWith("https://"))
                        if (!cfg.has("local_url")) cfg.put("local_url", cfg.getString("url"))
                        cfg.put("external_url", url); store.put("direct_config", cfg.toString())
                        status.text = "Endereço externo salvo. O Jarvis mantém o endereço local e usa o externo quando necessário."
                        DeviceSync.syncSoon()
                    }.onFailure { status.text = it.message } }.setNegativeButton("Cancelar", null).show()
            }.onFailure { status.text = "Pareie o canal primeiro." }
        }
        button("DESATIVAR CANAL DIRETO NESTE CELULAR") { SecureStore(this).put("direct_enabled", "false"); status.text = "Canal direto desativado. A conexão local/VPN anterior continua disponível." }
        button("VOLTAR") { finish() }
    }
    private fun pair() {
        if (pairing) return
        pairing = true; val value = ticket.text.toString(); status.text = "Pareando e verificando o certificado…"
        worker.execute {
            val result = runCatching { DirectChannel.enroll(applicationContext, value) }
            ui.post { pairing = false; if (!isFinishing && !isDestroyed) result.onSuccess {
                ticket.setText(""); status.text = "Canal pareado. Use Sincronizar agora para testar; acesso externo depende da configuração do PC e do roteador."; DeviceSync.syncSoon()
            }.onFailure { status.text = it.message } }
        }
    }
    @Deprecated("Android activity result compatibility")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val scan = IntentIntegrator.parseActivityResult(requestCode, resultCode, data)
        if (scan != null) {
            val value = scan.contents
            if (value == null) {
                status.text = "Leitura cancelada. Você pode escanear novamente ou importar o convite."
            } else if (value.startsWith("jarvis-direct:") && value.length <= 16000) {
                ticket.setText(value)
                status.text = "Convite lido. Toque em PAREAR CANAL PROTEGIDO."
            } else {
                status.text = "Este QR não é um convite do canal direto do Jarvis."
            }
            return
        }
        if (requestCode != 81 || resultCode != RESULT_OK) return
        worker.execute {
            val result = runCatching {
                contentResolver.openInputStream(data?.data ?: error("Arquivo indisponível")).use { source ->
                    require(source != null)
                    val bytes = ByteArray(16001); var count = 0
                    while (count < bytes.size) { val read = source.read(bytes, count, bytes.size - count); if (read < 0) break; count += read }
                    require(count <= 16000); String(bytes, 0, count)
                }
            }
            ui.post { if (!isFinishing && !isDestroyed) result.onSuccess { ticket.setText(it); status.text = "Convite lido. Toque em PAREAR CANAL PROTEGIDO." }.onFailure { status.text = "Não consegui ler o convite. Tente importar o arquivo novamente." } }
        }
    }
}
