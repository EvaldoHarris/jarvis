package com.evaldoharris.jarvis

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.view.TextureView
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.rtsp.RtspMediaSource
import androidx.media3.ui.PlayerView

@androidx.annotation.OptIn(UnstableApi::class)
class CameraActivity : Activity() {
    internal var cameraId = ""
    internal var channel = 1
    @Volatile internal var hasFrame = false
    @Volatile private var lastFrame = 0L
    @Volatile private var foreground = false
    @Volatile internal var error = ""
    private var player: ExoPlayer? = null
    private lateinit var view: PlayerView
    private lateinit var status: TextView
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON or WindowManager.LayoutParams.FLAG_SECURE)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(android.graphics.Color.BLACK) }
        root.setOnApplyWindowInsetsListener { v, insets -> val bars = insets.getInsets(android.view.WindowInsets.Type.systemBars()); v.setPadding(bars.left,bars.top,bars.right,bars.bottom); insets }
        status = TextView(this).apply { setTextColor(android.graphics.Color.CYAN); setPadding(16,16,16,16) }; root.addView(status)
        view = layoutInflater.inflate(R.layout.camera_player, root, false) as PlayerView
        root.addView(view, LinearLayout.LayoutParams(-1,0,1f))
        root.addView(Button(this).apply { text = "JARVIS"; setOnClickListener { startActivity(Intent(this@CameraActivity, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)) } })
        root.addView(Button(this).apply { text = "FECHAR CÂMERA"; setOnClickListener { finish() } })
        setContentView(root); CameraTools.current = this
        open(intent)
    }
    private fun open(intent: Intent) {
        try {
            val camera = CameraTools.selected(this, intent.getStringExtra("camera_id").orEmpty())
            val selectedChannel = intent.getIntExtra("channel", camera.optInt("channel", 1))
            val url = CameraTools.url(camera, selectedChannel)
            player?.release(); hasFrame = false; error = ""
            cameraId = camera.getString("id"); channel = selectedChannel
            status.text = "${camera.getString("name")} — canal $channel — conectando"
            androidx.media3.common.util.Log.setLogLevel(androidx.media3.common.util.Log.LOG_LEVEL_OFF)
            player = ExoPlayer.Builder(this).build().also { p ->
                view.player = p; p.volume = 0f
                p.setVideoFrameMetadataListener { _, _, _, _ -> lastFrame = android.os.SystemClock.elapsedRealtime(); hasFrame = true }
                p.addListener(object : Player.Listener {
                    override fun onRenderedFirstFrame() { hasFrame = true; status.text = "${camera.getString("name")} — canal $channel — AO VIVO" }
                    override fun onPlayerError(value: PlaybackException) {
                        hasFrame = false; error = "Câmera sem vídeo (código ${value.errorCode}). Confira rede, canal, credenciais e H.264."; status.text = error
                    }
                })
                p.setMediaSource(RtspMediaSource.Factory().setForceUseRtpTcp(true).createMediaSource(MediaItem.fromUri(url)))
                p.prepare(); p.playWhenReady = true
            }
        } catch (_: Exception) { error = "Não foi possível abrir a câmera. Confira a configuração em CASA."; status.text = error }
    }
    internal fun snapshot(): org.json.JSONObject {
        check(freshFrame() && error.isEmpty()) { "A câmera não tem um quadro recente. Abra o player e aguarde o vídeo." }
        val bitmap = (view.videoSurfaceView as? TextureView)?.bitmap ?: error("Imagem indisponível; abra o player da câmera.")
        return try { PhoneTools.result(true).put("image", PhoneTools.encode(bitmap)).put("channel", channel) } finally { bitmap.recycle() }
    }
    override fun onNewIntent(intent: Intent) { super.onNewIntent(intent); setIntent(intent); open(intent) }
    internal fun freshFrame() = foreground && hasFrame && android.os.SystemClock.elapsedRealtime() - lastFrame < 3000
    override fun onResume() { super.onResume(); foreground = true }
    override fun onPause() { foreground = false; super.onPause() }
    override fun onStop() { super.onStop(); player?.playWhenReady = false; hasFrame = false; lastFrame = 0L }
    override fun onRestart() { super.onRestart(); player?.playWhenReady = true }
    override fun onDestroy() { player?.release(); if (CameraTools.current === this) CameraTools.current = null; super.onDestroy() }
}
