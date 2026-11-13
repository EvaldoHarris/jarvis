package com.evaldoharris.jarvis

import android.app.*
import android.content.Context
import android.content.Intent
import android.graphics.BitmapFactory
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.WindowManager
import android.widget.*
import org.json.JSONObject
import java.util.concurrent.CopyOnWriteArraySet

internal object MonitorAlertState {
    private val handler = Handler(Looper.getMainLooper())
    val listeners = CopyOnWriteArraySet<() -> Unit>()
    data class Event(val id: String, val title: String, var status: String = "", var image: ByteArray? = null, var updated: Long = 0,
                     val frames: MutableList<MonitorClipStore.Frame> = mutableListOf(), var ended: Boolean = false)
    val events = linkedMapOf<String, Event>()
    var id = ""
    val title get() = events[id]?.title ?: "Alerta de câmera"
    val status get() = events[id]?.status ?: "Imagem indisponível"
    val image get() = events[id]?.image
    fun init(context: Context) {
        MonitorClipStore.init(context)
        if (events.isNotEmpty()) return
        for ((meta, frames) in MonitorClipStore.list()) {
            val key = meta.optString("alert_id")
            events[key] = Event(key, "${meta.optString("time")} · ${meta.optString("group")} / ${meta.optString("camera")}",
                status = "Gravação salva", frames = frames.toMutableList(), ended = true)
        }
        if (id.isEmpty()) id = events.keys.firstOrNull() ?: ""
    }
    fun receive(message: JSONObject): Boolean {
        val key = message.optString("alert_id")
        if (!key.matches(Regex("monitor_[a-f0-9]{24}"))) return false
        val first = message.optString("type") == "monitor_alert"
        if (!first && key !in events) return false
        val encoded = message.optString("image")
        if (encoded.length > 950000) return false
        val bytes = try { android.util.Base64.decode(encoded, android.util.Base64.NO_WRAP) } catch (_: Exception) { return false }
        if (bytes.size > 700000) return false
        if (first) {
            id = key
            runCatching { MonitorClipStore.begin(message) }
            events[key] = Event(key, "${message.optString("time").take(60)} · ${message.optString("group").take(70)} / ${message.optString("camera").take(100)}")
        }
        val event = events[key] ?: return false
        if (bytes.isNotEmpty()) event.image = bytes
        runCatching { MonitorClipStore.append(key, message.optDouble("offset", 0.0), bytes) }.getOrNull()?.let { event.frames.add(it) }
        event.ended = message.optBoolean("final")
        if (event.ended) MonitorClipStore.prune()
        event.status = if (message.optBoolean("final")) "Transmissão encerrada • última imagem recebida"
                 else "Reprodução do evento • ${message.optDouble("offset")} s em relação à detecção"
        event.updated = SystemClock.elapsedRealtime()
        listeners.forEach { it() }
        handler.postDelayed({
            val current = events[key]
            if (current != null && SystemClock.elapsedRealtime() - current.updated >= 60000) {
                current.image = null; current.status = "Gravação salva por até 24 horas"; listeners.forEach { it() }
            }
        }, 61000)
        return first
    }
}

class MonitorAlertActivity : Activity() {
    private lateinit var timeline: SeekBar
    private lateinit var pause: Button
    private var playing = true
    private var follow = true
    private var position = 0.0
    private var selectedId = ""
    private val clock = Handler(Looper.getMainLooper())
    private val tick = object : Runnable {
        override fun run() {
            if (playing && !follow) { position += .25; render() }
            clock.postDelayed(this, 250)
        }
    }
    private lateinit var selector: Spinner
    private var keys = listOf<String>()
    private lateinit var title: TextView
    private lateinit var image: ImageView
    private lateinit var status: TextView
    private var bitmap: android.graphics.Bitmap? = null
    private val refresh: () -> Unit = { render() }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        MonitorAlertState.init(applicationContext)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE or WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(Ui.BG_BOTTOM); setPadding(20, 40, 20, 20) }
        intent.getStringExtra("alert_id")?.takeIf { it in MonitorAlertState.events }?.let { MonitorAlertState.id = it }
        selector = Spinner(this)
        root.addView(selector)
        selector.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: AdapterView<*>?) {}
            override fun onItemSelected(parent: AdapterView<*>?, view: android.view.View?, position: Int, itemId: Long) {
                if (position != selector.selectedItemPosition) return
                keys.getOrNull(position)?.let { if (it != MonitorAlertState.id) { MonitorAlertState.id = it; render() } }
            }
        }
        title = TextView(this).apply { setTextColor(Ui.CYAN); textSize = 20f }; root.addView(title)
        status = TextView(this).apply { setTextColor(Ui.TEXT) }; root.addView(status)
        image = ImageView(this).apply { scaleType = ImageView.ScaleType.FIT_CENTER; contentDescription = "Imagens do evento na câmera de segurança" }
        root.addView(image, LinearLayout.LayoutParams(-1, 0, 1f))
        timeline = SeekBar(this)
        timeline.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onStartTrackingTouch(bar: SeekBar?) { playing = false; follow = false }
            override fun onStopTrackingTouch(bar: SeekBar?) {}
            override fun onProgressChanged(bar: SeekBar?, progress: Int, fromUser: Boolean) {
                if (fromUser) { position = (MonitorAlertState.events[MonitorAlertState.id]?.frames?.firstOrNull()?.offset ?: 0.0) + progress / 1000.0; render() }
            }
        })
        root.addView(timeline)
        val buttons = LinearLayout(this)
        buttons.addView(Button(this).apply { text = "−5 s"; setOnClickListener { follow = false; position -= 5; render() } })
        pause = Button(this).apply { text = "PAUSAR"; setOnClickListener {
            follow = false; playing = !playing
            val frames = MonitorAlertState.events[MonitorAlertState.id]?.frames
            if (playing && frames?.isNotEmpty() == true && position >= frames.last().offset) position = frames.first().offset
            render()
        } }
        buttons.addView(pause)
        buttons.addView(Button(this).apply { text = "+5 s"; setOnClickListener { follow = false; position += 5; render() } })
        buttons.addView(Button(this).apply { text = "ÚLTIMA"; setOnClickListener { follow = true; playing = true; render() } })
        root.addView(buttons)
        root.addView(Button(this).apply { text = "FECHAR ALERTA"; setOnClickListener { finish() } })
        setContentView(root)
    }
    override fun onStart() { super.onStart(); MonitorAlertState.listeners.add(refresh); render(); clock.postDelayed(tick, 250) }
    override fun onStop() { MonitorAlertState.listeners.remove(refresh); clock.removeCallbacks(tick); super.onStop() }
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        intent.getStringExtra("alert_id")?.takeIf { it in MonitorAlertState.events }?.let { MonitorAlertState.id = it }
        render()
    }
    private fun render() {
        val nextKeys = MonitorAlertState.events.keys.toList()
        if (keys != nextKeys) {
            keys = nextKeys
            selector.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, keys.map { MonitorAlertState.events[it]?.title ?: "Câmera" })
        }
        keys.indexOf(MonitorAlertState.id).takeIf { it >= 0 }?.let { selector.setSelection(it) }
        title.text = MonitorAlertState.title
        val event = MonitorAlertState.events[MonitorAlertState.id]
        val frames = event?.frames.orEmpty()
        if (selectedId != MonitorAlertState.id) {
            selectedId = MonitorAlertState.id; follow = event?.ended != true; playing = true
            position = frames.firstOrNull()?.offset ?: 0.0
        }
        var bytes: ByteArray? = event?.image
        if (frames.isNotEmpty()) {
            position = if (follow) frames.last().offset else position.coerceIn(frames.first().offset, frames.last().offset)
            val frame = frames.lastOrNull { it.offset <= position } ?: frames.first()
            bytes = MonitorClipStore.read(MonitorAlertState.id, frame)
            timeline.max = ((frames.last().offset - frames.first().offset) * 1000).toInt()
            timeline.progress = ((position - frames.first().offset) * 1000).toInt()
            if (!follow && event?.ended == true && position >= frames.last().offset) playing = false
        }
        pause.text = if (playing) "PAUSAR" else "REPRODUZIR"
        status.text = "${if (playing) "Reproduzindo" else "Pausado"} · ${"%.1f".format(position)} s · ${if (event?.ended == true) "captura encerrada" else "recebendo imagens"}"
        val next = bytes?.let { BitmapFactory.decodeByteArray(it, 0, it.size) }
        image.setImageBitmap(next); bitmap?.recycle(); bitmap = next
    }
    override fun onDestroy() { image.setImageDrawable(null); bitmap?.recycle(); super.onDestroy() }
    companion object {
        fun notify(context: Context) {
            val manager = context.getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(NotificationChannel("camera_monitor", "Alertas das câmeras", NotificationManager.IMPORTANCE_HIGH))
            val intent = Intent(context, MonitorAlertActivity::class.java).putExtra("alert_id", MonitorAlertState.id).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            val notificationId = MonitorAlertState.id.hashCode()
            val open = PendingIntent.getActivity(context, notificationId, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            val builder = Notification.Builder(context, "camera_monitor").setSmallIcon(R.drawable.ic_reactor)
                .setContentTitle("Detecção na câmera: ${MonitorAlertState.title}")
                .setContentText("Pessoa ou veículo detectado • toque para acompanhar")
                .setVisibility(Notification.VISIBILITY_PRIVATE).setContentIntent(open).setAutoCancel(true).setTimeoutAfter(86400000)
            MonitorAlertState.image?.let { bytes -> BitmapFactory.decodeByteArray(bytes, 0, bytes.size)?.let {
                builder.setStyle(Notification.BigPictureStyle().bigPicture(it).setSummaryText("Toque para acompanhar o evento"))
            } }
            try { manager.notify(notificationId, builder.build()) } catch (_: SecurityException) {
                AppState.message("SYS", "Ative as notificações do Jarvis para receber alertas das câmeras.")
            }
            if (AppState.mainVisible) context.startActivity(intent)
        }
    }
}
