package com.evaldoharris.jarvis

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionConfig
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.media.AudioManager
import android.widget.CheckBox
import android.widget.SeekBar
import android.widget.TextView

class VideoTranslationActivity : FeatureActivity() {
    private lateinit var status: TextView
    private lateinit var caption: TextView
    private lateinit var audio: CheckBox
    @Volatile private var preparing = false
    private var requesting = false
    private var syncing = false
    private var preview:TranslationNarrator?=null
    private val refresh: () -> Unit = {
        status.text = VideoTranslationState.status
        caption.text = VideoTranslationState.caption
        syncing = true; audio.isChecked = VideoTranslationState.audio; syncing = false
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        getSystemService(android.app.NotificationManager::class.java).cancel(32)
        volumeControlStream=AssistantAudio.attributes().volumeControlStream
        line("TRADUÇÃO DE VÍDEOS — INGLÊS → PORTUGUÊS").textSize = 19f
        line("Reconhecimento, tradução e voz locais, sem enviar áudio ou texto ao Gemini. Prepare os modelos uma vez com internet (reconhecimento: cerca de 40 MB, mais os modelos de tradução). Depois, funciona offline e sem o PC.")
        line("Ao iniciar, o Android pedirá autorização de captura. O áudio do vídeo é traduzido sem gravar a tela. O microfone fica ativo com reconhecimento local apenas para ouvir Jarvis, pare a tradução. Alguns aplicativos bloqueiam captura. A própria voz do Jarvis fica excluída.")
        status = line(VideoTranslationState.status)
        caption = line(VideoTranslationState.caption).apply { textSize = 21f }
        audio = CheckBox(this).apply {
            text = "Ouvir tradução ao vivo"; setTextColor(Ui.TEXT); isChecked = VideoTranslationState.audio
            setOnCheckedChangeListener { button, checked ->
                if (!syncing) {
                    VideoTranslationState.audio = checked
                    if (VideoTranslationState.active) startService(Intent(this@VideoTranslationActivity, VideoTranslationService::class.java)
                        .setAction(if (checked) VideoTranslationService.AUDIO_ON else VideoTranslationService.AUDIO_OFF))
                }
            }
        }; column.addView(audio)
        button("PREPARAR MODELOS OFFLINE") {
            if (preparing || VideoTranslationState.active) return@button
            preparing = true
            worker.execute {
                try { TranslationModels.prepare(this) { text -> VideoTranslationState.update(text) } }
                catch (e: Exception) { VideoTranslationState.update("Falha na preparação: ${e.message}") }
                finally { preparing = false }
            }
        }
        button("INICIAR TRADUÇÃO") { begin() }
        button("PARAR TRADUÇÃO") { stopService(Intent(this, VideoTranslationService::class.java)) }
        val store=SecureStore(this)
        val percent=store.get("translation_volume","100").toIntOrNull()?.coerceIn(0,100)?:100
        val level=line("Volume da tradução: $percent%")
        column.addView(SeekBar(this).apply {
            max=100;progress=percent
            setOnSeekBarChangeListener(object:SeekBar.OnSeekBarChangeListener{
                override fun onStartTrackingTouch(bar:SeekBar?){}
                override fun onStopTrackingTouch(bar:SeekBar?){}
                override fun onProgressChanged(bar:SeekBar?,value:Int,fromUser:Boolean){
                    if(!fromUser)return
                    level.text="Volume da tradução: $value%";store.put("translation_volume",value.toString());preview?.setVolume(value)
                    if(VideoTranslationState.active)startService(Intent(this@VideoTranslationActivity,VideoTranslationService::class.java).setAction(VideoTranslationService.VOLUME).putExtra("percent",value))
                }
            })
        })
        button("OUVIR NOVA VOZ") {
            if(VideoTranslationState.active)return@button
            preview?.close()
            preview=TranslationNarrator(this){message->ui.post{status.text=message}}
            preview?.offer("Olá. Esta é a nova voz masculina da tradução do Jarvis.")
        }
        line("A voz usa o mesmo canal do assistente de IA; a barra ajusta somente a tradução. Diga Jarvis, pare a tradução para encerrar. Um toque no reator permite falar sem dizer Jarvis; dois toques abrem o app. A voz é local e não é uma cópia da Charon.")
        if(intent.getBooleanExtra("start_translation",false))ui.post{begin()}
    }
    private fun begin() {
        if (preparing || requesting || VideoTranslationState.active) return
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 71); return
        }
        requesting = true
        worker.execute {
            try {
                check(TranslationModels.ready(this)) { "Toque em PREPARAR MODELOS OFFLINE antes de iniciar." }
                ui.post {
                    if (isFinishing || isDestroyed) return@post
                    val manager = getSystemService(MediaProjectionManager::class.java)
                    @Suppress("DEPRECATION")
                    startActivityForResult(if (Build.VERSION.SDK_INT >= 34) manager.createScreenCaptureIntent(MediaProjectionConfig.createConfigForDefaultDisplay())
                        else manager.createScreenCaptureIntent(), 72)
                }
            } catch (e: Exception) { ui.post { requesting = false; status.text = e.message } }
        }
    }
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 71 && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) begin()
    }
    @Deprecated("Activity result bridge")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == 72) requesting = false
        if (requestCode == 72 && resultCode == Activity.RESULT_OK && data != null) {
            runCatching { startForegroundService(Intent(this, VideoTranslationService::class.java)
                .putExtra("consent", data).putExtra("result", resultCode).putExtra("audio", audio.isChecked)) }
                .onFailure { status.text = "Não foi possível iniciar: ${it.message}" }
        }
    }
    override fun onNewIntent(intent:Intent) {
        super.onNewIntent(intent);setIntent(intent)
        if(intent.getBooleanExtra("start_translation",false))begin()
    }
    override fun onResume() { super.onResume(); AppState.listeners.add(refresh); refresh() }
    override fun onPause() { preview?.close();preview=null;AppState.listeners.remove(refresh); super.onPause() }
}
