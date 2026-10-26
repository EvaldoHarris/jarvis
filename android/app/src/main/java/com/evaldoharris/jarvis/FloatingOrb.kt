package com.evaldoharris.jarvis

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.Typeface
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin

/** Estado visual compartilhado pelo rosto e pelo atalho flutuante. */
enum class JarvisMood(val label: String, val color: Int) {
    IDLE("", Ui.CYAN), LISTENING("OUVINDO", Ui.GREEN), THINKING("PENSANDO", Ui.VIOLET), SPEAKING("FALANDO", Ui.CYAN);
    companion object {
        fun current(): JarvisMood = when {
            AppState.audioBusy -> SPEAKING
            AppState.assistantBusy || AppState.phase == "PENSANDO" || AppState.expectedPhoneReply.isNotEmpty() -> THINKING
            AppState.readyForCommand() || AppState.manualListening -> LISTENING
            else -> IDLE
        }
    }
}

/** Mini-reator animado usado no atalho flutuante. */
class MiniReactorView(context: Context) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val arc = RectF()
    private var turn = 0f
    private var time = 0f
    var mood = JarvisMood.IDLE
        set(value) { if (field != value) { field = value; invalidate() } }

    private fun alpha(color: Int, a: Int) = Color.argb(a, Color.red(color), Color.green(color), Color.blue(color))

    override fun onDraw(canvas: Canvas) {
        val cx = width / 2f; val cy = height / 2f; val r = min(width, height) * .46f
        val color = mood.color
        // Fundo de vidro escuro
        paint.style = Paint.Style.FILL; paint.shader = null; paint.color = Color.argb(225, 4, 12, 24)
        canvas.drawCircle(cx, cy, r, paint)
        paint.shader = RadialGradient(cx, cy, r, intArrayOf(alpha(color, 90), Color.TRANSPARENT), null, Shader.TileMode.CLAMP)
        canvas.drawCircle(cx, cy, r, paint); paint.shader = null
        // Anéis
        paint.style = Paint.Style.STROKE; paint.strokeCap = Paint.Cap.ROUND
        paint.strokeWidth = r * .09f; paint.color = alpha(color, 235)
        arc.set(cx - r * .82f, cy - r * .82f, cx + r * .82f, cy + r * .82f)
        repeat(3) { canvas.drawArc(arc, it * 120f + turn, 70f, false, paint) }
        paint.strokeWidth = r * .04f; paint.color = alpha(color, 130)
        arc.set(cx - r * .6f, cy - r * .6f, cx + r * .6f, cy + r * .6f)
        repeat(4) { canvas.drawArc(arc, it * 90f - turn * 1.4f, 50f, false, paint) }
        // Ondas quando está falando
        if (mood == JarvisMood.SPEAKING) {
            paint.strokeWidth = r * .05f; paint.color = alpha(color, 220)
            repeat(16) { b ->
                val a = b * Math.PI / 8
                val amp = r * (.06f + .12f * ((sin(time * 11f + b * 1.9f) + 1f) / 2f))
                val r0 = r * .3f
                canvas.drawLine(cx + cos(a).toFloat() * r0, cy + sin(a).toFloat() * r0, cx + cos(a).toFloat() * (r0 + amp), cy + sin(a).toFloat() * (r0 + amp), paint)
            }
        }
        // Núcleo pulsante
        val pulse = (sin(time * if (mood == JarvisMood.IDLE) 2f else 5f) + 1f) / 2f
        val core = r * (.24f + .05f * pulse)
        paint.style = Paint.Style.FILL
        paint.shader = RadialGradient(cx, cy, core, intArrayOf(Color.WHITE, alpha(color, 220), Color.TRANSPARENT), floatArrayOf(0f, .45f, 1f), Shader.TileMode.CLAMP)
        canvas.drawCircle(cx, cy, core, paint); paint.shader = null
        // Borda
        paint.style = Paint.Style.STROKE; paint.strokeWidth = r * .03f; paint.color = alpha(color, 160)
        canvas.drawCircle(cx, cy, r * .98f, paint)

        time += .05f
        turn += when (mood) { JarvisMood.THINKING -> 6f; JarvisMood.SPEAKING -> 3f; JarvisMood.LISTENING -> 2.2f; JarvisMood.IDLE -> .6f }
        // Parado, anima devagar para economizar bateria.
        if (isShown) { if (mood == JarvisMood.IDLE) postInvalidateDelayed(80) else postInvalidateOnAnimation() }
    }
}

/** Atalho flutuante: etiqueta de estado + mini-reator. */
class FloatingOrb(context: Context) : LinearLayout(context) {
    private val density = context.resources.displayMetrics.density
    private fun dp(v: Int) = (v * density).toInt()
    val orb = MiniReactorView(context)
    private val label = TextView(context).apply {
        textSize = 10f; letterSpacing = .18f; typeface = Typeface.create("sans-serif-medium", Typeface.BOLD)
        setPadding(dp(12), dp(6), dp(12), dp(6)); visibility = GONE
    }
    init {
        orientation = HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
        setPadding(dp(4), dp(4), dp(6), dp(4))
        addView(label, LayoutParams(-2, -2).apply { rightMargin = dp(6) })
        addView(orb, LayoutParams(dp(46), dp(46)))
    }
    /** Encostado à esquerda, a etiqueta fica à direita do reator (e vice-versa). */
    fun setSide(left: Boolean) {
        removeAllViews()
        if (left) {
            addView(orb, LayoutParams(dp(46), dp(46)))
            addView(label, LayoutParams(-2, -2).apply { leftMargin = dp(6) })
        } else {
            addView(label, LayoutParams(-2, -2).apply { rightMargin = dp(6) })
            addView(orb, LayoutParams(dp(46), dp(46)))
        }
    }
    fun render(mood: JarvisMood) {
        orb.mood = mood
        if (mood == JarvisMood.IDLE) { label.visibility = GONE; return }
        label.text = mood.label; label.setTextColor(mood.color)
        label.background = Ui.pill(Color.argb(225, 4, 12, 24), mood.color, strokeWidth = dp(1))
        label.visibility = VISIBLE
    }
}
