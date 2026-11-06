package com.evaldoharris.jarvis

import android.app.Activity
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.BitmapFactory
import android.os.Bundle
import android.view.WindowManager
import android.widget.Button
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView

class PresenceAlertActivity : Activity() {
    private lateinit var image: ImageView
    private lateinit var status: TextView
    private val refresh: () -> Unit = { render() }
    private var bitmap: android.graphics.Bitmap? = null
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE or WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(Ui.BG_BOTTOM); setPadding(20, 40, 20, 20) }
        root.addView(TextView(this).apply { text = PresencePreviewState.NOTICE; textSize = 20f; setTextColor(Ui.CYAN) })
        root.addView(TextView(this).apply { text = "O rosto do proprietário não foi confirmado. Confira a imagem: isso pode ser uma falha de reconhecimento e não comprova uso indevido do PC."; setTextColor(Ui.TEXT) })
        status = TextView(this).apply { setTextColor(Ui.GREEN) }; root.addView(status)
        image = ImageView(this).apply { scaleType = ImageView.ScaleType.FIT_CENTER; contentDescription = "Prévia da webcam do computador" }
        root.addView(image, LinearLayout.LayoutParams(-1, 0, 1f))
        root.addView(Button(this).apply { text = "FECHAR PRÉVIA"; setOnClickListener { finish() } })
        setContentView(root)
    }
    override fun onStart() { super.onStart(); PresencePreviewState.listeners.add(refresh); render() }
    override fun onStop() { PresencePreviewState.listeners.remove(refresh); super.onStop() }
    private fun render() {
        val bytes = PresencePreviewState.image
        val next = bytes?.let { BitmapFactory.decodeByteArray(it, 0, it.size) }
        image.setImageBitmap(next); bitmap?.recycle(); bitmap = next
        val fresh = android.os.SystemClock.elapsedRealtime() - PresencePreviewState.updated < 5000
        status.text = if (next == null) "Prévia indisponível ou expirada" else if (PresencePreviewState.live && fresh) "WEBCAM • atualização ao vivo" else "Última imagem recebida • prévia encerrada"
    }
    override fun onDestroy() { image.setImageDrawable(null); bitmap?.recycle(); super.onDestroy() }
    companion object {
        fun notify(context: Context) {
            val manager = context.getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(NotificationChannel("presence_alert", "Pessoa no computador", NotificationManager.IMPORTANCE_HIGH))
            val intent = Intent(context, PresenceAlertActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            val open = PendingIntent.getActivity(context, 41, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            val notification = Notification.Builder(context, "presence_alert").setSmallIcon(R.drawable.ic_reactor)
                .setContentTitle("Pessoa não identificada no computador").setContentText(PresencePreviewState.NOTICE)
                .setVisibility(Notification.VISIBILITY_PRIVATE).setContentIntent(open).setAutoCancel(true).setTimeoutAfter(60000)
            PresencePreviewState.image?.let { bytes -> BitmapFactory.decodeByteArray(bytes, 0, bytes.size)?.let { picture ->
                notification.setStyle(Notification.BigPictureStyle().bigPicture(picture).setSummaryText("Toque para ver a webcam • reconhecimento inconclusivo"))
            } }
            try { manager.notify(41, notification.build()) } catch (_: SecurityException) { AppState.message("SYS", "Ative as notificações do Jarvis para receber o alerta da webcam.") }
            if (AppState.mainVisible) context.startActivity(intent)
        }
    }
}
