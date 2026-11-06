package com.evaldoharris.jarvis

import android.accessibilityservice.AccessibilityService
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.view.Gravity
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import android.widget.TextView
import java.io.File
import java.util.concurrent.Executors
import android.util.Base64

class JarvisAccessibilityService : AccessibilityService() {
    companion object {
        @Volatile var current: JarvisAccessibilityService? = null
        val windowVersion=java.util.concurrent.atomic.AtomicLong()
        @Volatile var lastChange=0L
    }
    private var bubble: FloatingOrb? = null
    private val main = android.os.Handler(android.os.Looper.getMainLooper())
    private var overlayManager:WindowManager?=null
    private var overlayParams:WindowManager.LayoutParams?=null
    private var attachErrorLogged=false
    private val recoverOverlay=object:Runnable {
        override fun run() {
            if(current!==this@JarvisAccessibilityService)return
            attachOverlay();refreshWake()
            main.postDelayed(this,2000)
        }
    }
    private val executor = Executors.newSingleThreadExecutor()
    private val refreshWake:()->Unit={
        bubble?.let{view->
            // Dentro do app o rosto já mostra o estado; o atalho só aparece nos outros apps.
            view.visibility=if(AppState.mainVisible)android.view.View.GONE else android.view.View.VISIBLE
            view.render(JarvisMood.current())
        }
    }
    override fun onServiceConnected() {
        main.removeCallbacks(recoverOverlay)
        bubble?.let { old -> runCatching { overlayManager?.removeView(old) } }
        current = this
        AppState.update()
        val manager = getSystemService(WINDOW_SERVICE) as WindowManager
        bubble = FloatingOrb(this).apply {
            contentDescription = "JARVIS: um toque para falar; dois toques para abrir o aplicativo; segure para analisar a tela"
            setOnClickListener {
                if(!WakeListeningService.arm(this@JarvisAccessibilityService))openAssistant(listen=true)
            }
            setOnLongClickListener {
                executor.execute {
                    val result = PhoneTools.execute(this@JarvisAccessibilityService, "screen", org.json.JSONObject())
                    if (result.optBoolean("ok")) {
                        val file = File(cacheDir, "observed_screen.jpg")
                        file.writeBytes(Base64.decode(result.getString("image"), Base64.NO_WRAP))
                        openAssistant(file.absolutePath)
                    } else { AppState.message("SYS", result.optString("error")); openAssistant() }
                }
                true
            }
        }
        val prefs = getSharedPreferences("floating_orb", MODE_PRIVATE)
        var left = prefs.getBoolean("left", false)
        val screenHeight = resources.displayMetrics.heightPixels
        val params = WindowManager.LayoutParams(WindowManager.LayoutParams.WRAP_CONTENT, WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY, WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT).apply {
            // x conta a partir da borda em que o atalho está encostado.
            gravity = Gravity.TOP or if (left) Gravity.START else Gravity.END
            title="JARVIS_FloatingReactor"
            x = 0; y = prefs.getInt("y", screenHeight / 2).coerceIn(0,(screenHeight-(60*resources.displayMetrics.density).toInt()).coerceAtLeast(0))
        }
        bubble?.setSide(left)
        bubble?.let { view -> enableDragging(view, params, manager) { newLeft, newY ->
            left = newLeft; prefs.edit().putBoolean("left", newLeft).putInt("y", newY).apply()
        } }
        overlayManager=manager;overlayParams=params
        attachOverlay()
        AppState.listeners.add(refreshWake);refreshWake()
        main.postDelayed(recoverOverlay,2000)
    }
    /** A transient WindowManager failure must not permanently discard the reactor. */
    private fun attachOverlay() {
        val view=bubble?:return
        if(view.isAttachedToWindow)return
        try {
            overlayManager?.addView(view,overlayParams)
            attachErrorLogged=false
        } catch(e:Exception) {
            if(!attachErrorLogged)android.util.Log.w("JarvisOverlay","Could not attach floating reactor; will retry",e)
            attachErrorLogged=true
        }
    }
    internal fun reactorVisible()=bubble?.isAttachedToWindow==true&&bubble?.isShown==true
    internal fun reactorBounds():android.graphics.Rect? {
        val view=bubble?:return null
        if(!view.isShown)return null
        val location=IntArray(2);view.getLocationOnScreen(location)
        return android.graphics.Rect(location[0],location[1],location[0]+view.width,location[1]+view.height)
    }
    /** Arrastar move o atalho; ao soltar ele encosta na borda mais próxima. Toque e toque longo seguem normais. */
    @android.annotation.SuppressLint("ClickableViewAccessibility")
    private fun enableDragging(view: FloatingOrb, params: WindowManager.LayoutParams, manager: WindowManager, saved: (Boolean, Int) -> Unit) {
        val slop = android.view.ViewConfiguration.get(this).scaledTouchSlop
        var startX = 0f; var startY = 0f; var originY = 0; var dragging = false
        val taps=android.view.GestureDetector(this,object:android.view.GestureDetector.SimpleOnGestureListener(){
            override fun onDown(event:android.view.MotionEvent)=true
            override fun onSingleTapConfirmed(event:android.view.MotionEvent):Boolean { android.util.Log.d("JarvisReactor","single_tap_confirmed");view.performClick();return true }
            override fun onDoubleTap(event:android.view.MotionEvent):Boolean { android.util.Log.d("JarvisReactor","double_tap");openAssistant();return true }
            override fun onLongPress(event:android.view.MotionEvent){view.performLongClick()}
        })
        view.setOnTouchListener { _, event ->
            val metrics = resources.displayMetrics
            when (event.actionMasked) {
                android.view.MotionEvent.ACTION_DOWN -> { startX = event.rawX; startY = event.rawY; originY = params.y; dragging = false;taps.onTouchEvent(event);true }
                android.view.MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX - startX; val dy = event.rawY - startY
                    if (!dragging && (kotlin.math.abs(dx) > slop || kotlin.math.abs(dy) > slop)) {
                        dragging = true;view.cancelLongPress();view.isPressed=false
                        val cancel=android.view.MotionEvent.obtain(event);cancel.action=android.view.MotionEvent.ACTION_CANCEL;taps.onTouchEvent(cancel);cancel.recycle()
                    }
                    if (dragging) {
                        // Durante o arraste, posição livre a partir do canto superior esquerdo.
                        params.gravity = Gravity.TOP or Gravity.START
                        params.x = (event.rawX - view.width / 2f).toInt().coerceIn(0, (metrics.widthPixels - view.width).coerceAtLeast(0))
                        params.y = (originY + dy).toInt().coerceIn(0, (metrics.heightPixels - view.height).coerceAtLeast(0))
                        try { manager.updateViewLayout(view, params) } catch (_: Exception) {}
                    }
                    if(!dragging)taps.onTouchEvent(event)
                    true
                }
                android.view.MotionEvent.ACTION_UP, android.view.MotionEvent.ACTION_CANCEL -> {
                    if (!dragging) {taps.onTouchEvent(event);return@setOnTouchListener true}
                    val left = event.rawX < metrics.widthPixels / 2f
                    params.gravity = Gravity.TOP or if (left) Gravity.START else Gravity.END
                    params.x = 0
                    view.setSide(left)
                    try { manager.updateViewLayout(view, params) } catch (_: Exception) {}
                    saved(left, params.y)
                    dragging = false
                    true
                }
                else -> {if(!dragging)taps.onTouchEvent(event);true}
            }
        }
    }
    private fun openAssistant(image: String? = null,listen:Boolean=false) {
        startActivity(Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            .apply { if (image != null) putExtra("screen_image", image);if(listen)putExtra("activate_listening",true) })
    }
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        lastChange=android.os.SystemClock.elapsedRealtime();windowVersion.incrementAndGet()
    }
    override fun onInterrupt() = Unit
    override fun onDestroy() {
        main.removeCallbacksAndMessages(null)
        if (current === this) current = null
        AppState.listeners.remove(refreshWake)
        bubble?.let { try { (getSystemService(WINDOW_SERVICE) as WindowManager).removeView(it) } catch (_: Exception) {} }
        bubble=null;overlayManager=null;overlayParams=null
        executor.shutdownNow()
        AppState.update()
        super.onDestroy()
    }
}
