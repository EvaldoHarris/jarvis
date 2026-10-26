package com.evaldoharris.jarvis

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

/** Paleta e componentes visuais compartilhados (tema futurista escuro). */
object Ui {
    val BG_TOP = Color.rgb(4, 10, 22)
    val BG_BOTTOM = Color.rgb(1, 3, 8)
    val CYAN = Color.rgb(0, 229, 255)
    val GREEN = Color.rgb(0, 255, 170)
    val VIOLET = Color.rgb(150, 110, 255)
    val TEXT = Color.rgb(214, 236, 245)
    val MUTED = Color.rgb(98, 132, 150)
    val GLASS = Color.argb(150, 10, 28, 44)
    val LINE = Color.argb(110, 0, 200, 235)

    private fun Context.dp(v: Int) = (resources.displayMetrics.density * v).toInt()

    fun backdrop() = GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, intArrayOf(BG_TOP, BG_BOTTOM))

    fun pill(fill: Int, stroke: Int, radius: Float = 999f, strokeWidth: Int = 2) = GradientDrawable().apply {
        setColor(fill); setStroke(strokeWidth, stroke); cornerRadius = radius
    }

    fun iconButton(context: Context, symbol: String, description: String, filled: Boolean = false, action: () -> Unit) = Button(context).apply {
        text = symbol; contentDescription = description; textSize = 17f; isAllCaps = false
        setPadding(0, 0, 0, 0); minWidth = 0; minHeight = 0; minimumWidth = 0; minimumHeight = 0
        stateListAnimator = null; gravity = Gravity.CENTER
        setTextColor(if (filled) BG_BOTTOM else CYAN)
        background = GradientDrawable().apply {
            shape = GradientDrawable.OVAL
            if (filled) colors = intArrayOf(CYAN, GREEN) else setColor(Color.TRANSPARENT)
            if (filled) gradientType = GradientDrawable.LINEAR_GRADIENT
        }
        setOnClickListener { action() }
    }

    /** Balão de conversa: usuário à direita, JARVIS à esquerda, sistema centralizado. */
    fun bubble(context: Context, who: String, body: String): LinearLayout {
        val user = who.startsWith("Você") || who.substringAfterLast("/").trim().equals("user", ignoreCase = true)
        val system = who == "SYS"
        val row = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            gravity = when { user -> Gravity.END; system -> Gravity.CENTER_HORIZONTAL; else -> Gravity.START }
            setPadding(0, context.dp(4), 0, context.dp(4))
        }
        if (!system) row.addView(TextView(context).apply {
            text = who.uppercase(); textSize = 9f; letterSpacing = .2f; typeface = Typeface.MONOSPACE
            setTextColor(if (user) MUTED else CYAN); setPadding(context.dp(10), 0, context.dp(10), context.dp(2))
        })
        val max = (context.resources.displayMetrics.widthPixels * .80f).toInt()
        row.addView(TextView(context).apply {
            text = body; setTextIsSelectable(true); maxWidth = max
            textSize = if (system) 11f else 14.5f
            setLineSpacing(0f, 1.15f)
            setTextColor(if (system) MUTED else TEXT)
            setPadding(context.dp(14), context.dp(10), context.dp(14), context.dp(10))
            val r = context.dp(18).toFloat(); val s = context.dp(4).toFloat()
            background = GradientDrawable().apply {
                when {
                    system -> { setColor(Color.TRANSPARENT); cornerRadius = r }
                    user -> { colors = intArrayOf(Color.argb(200, 0, 96, 130), Color.argb(200, 0, 70, 110)); cornerRadii = floatArrayOf(r, r, s, s, r, r, r, r) }
                    else -> { setColor(GLASS); setStroke(2, LINE); cornerRadii = floatArrayOf(s, s, r, r, r, r, r, r) }
                }
            }
        }, LinearLayout.LayoutParams(-2, -2))
        return row
    }
}
