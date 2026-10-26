package com.evaldoharris.jarvis

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.Typeface
import android.view.View
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin

/** Rosto do JARVIS: anéis holográficos, núcleo pulsante e cor conforme o estado. */
class ReactorView(context: Context) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val arc = RectF()
    private var turn = 0f
    private var time = 0f
    init { contentDescription = "Rosto animado do JARVIS" }

    private fun stateColor(): Int = JarvisMood.current().color
    private fun alpha(color: Int, a: Int) = Color.argb(a, Color.red(color), Color.green(color), Color.blue(color))

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val cx = width / 2f; val cy = height / 2f; val radius = min(width, height) * .44f
        val color = stateColor()
        val speaking = AppState.audioBusy
        val pulse = (sin(time * if (speaking) 9f else 2.2f) + 1f) / 2f

        // Halo
        paint.style = Paint.Style.FILL
        paint.shader = RadialGradient(cx, cy, radius * 1.15f, intArrayOf(alpha(color, 70), alpha(color, 18), Color.TRANSPARENT), floatArrayOf(0f, .55f, 1f), Shader.TileMode.CLAMP)
        canvas.drawCircle(cx, cy, radius * 1.15f, paint); paint.shader = null

        // Anéis segmentados girando em sentidos opostos
        paint.style = Paint.Style.STROKE; paint.strokeCap = Paint.Cap.ROUND
        val rings = floatArrayOf(.98f, .86f, .74f, .62f)
        rings.forEachIndexed { i, f ->
            val r = radius * f
            arc.set(cx - r, cy - r, cx + r, cy + r)
            paint.color = alpha(color, if (i % 2 == 0) 230 else 120)
            paint.strokeWidth = if (i == 1) radius * .035f else radius * .012f
            val segments = if (i == 1) 3 else 6 - i
            val sweep = 360f / segments
            val dir = if (i % 2 == 0) 1 else -1
            repeat(segments) { s -> canvas.drawArc(arc, s * sweep + turn * dir * (1f + i * .3f), sweep * .62f, false, paint) }
        }

        // Marcadores externos
        paint.strokeWidth = radius * .008f
        repeat(72) { t ->
            val a = t * Math.PI / 36 + turn * .004
            val inner = radius * if (t % 6 == 0) 1.04f else 1.07f
            val outer = radius * 1.1f
            paint.color = alpha(color, if (t % 6 == 0) 200 else 70)
            canvas.drawLine(cx + cos(a).toFloat() * inner, cy + sin(a).toFloat() * inner, cx + cos(a).toFloat() * outer, cy + sin(a).toFloat() * outer, paint)
        }

        // Ondas de voz ao redor do núcleo quando está falando
        if (speaking) {
            paint.strokeWidth = radius * .02f
            repeat(36) { b ->
                val a = b * Math.PI / 18
                val amp = radius * (.05f + .09f * ((sin(time * 11f + b * 1.7f) + 1f) / 2f))
                val r0 = radius * .44f
                paint.color = alpha(color, 200)
                canvas.drawLine(cx + cos(a).toFloat() * r0, cy + sin(a).toFloat() * r0, cx + cos(a).toFloat() * (r0 + amp), cy + sin(a).toFloat() * (r0 + amp), paint)
            }
        }

        // Núcleo
        paint.style = Paint.Style.FILL
        val core = radius * (.36f + .04f * pulse)
        paint.shader = RadialGradient(cx, cy, core, intArrayOf(Color.WHITE, alpha(color, 230), alpha(color, 40), Color.TRANSPARENT), floatArrayOf(0f, .25f, .7f, 1f), Shader.TileMode.CLAMP)
        canvas.drawCircle(cx, cy, core, paint); paint.shader = null
        paint.style = Paint.Style.STROKE; paint.strokeWidth = radius * .01f; paint.color = alpha(Color.WHITE, 160)
        canvas.drawCircle(cx, cy, radius * .4f, paint)

        // Rótulo
        paint.style = Paint.Style.FILL; paint.color = alpha(Color.WHITE, 230)
        paint.textSize = radius * .12f; paint.textAlign = Paint.Align.CENTER; paint.letterSpacing = .3f
        paint.typeface = Typeface.create("sans-serif-light", Typeface.BOLD)
        canvas.drawText("JARVIS", cx, cy + paint.textSize * .35f, paint)
        paint.letterSpacing = 0f

        time += .04f
        turn += when { AppState.assistantBusy -> 2.4f; speaking -> 1.4f; AppState.readyForCommand() -> 1f; else -> .35f }
        if (isShown) postInvalidateOnAnimation()
    }
}
