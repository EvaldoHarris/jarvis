package com.evaldoharris.jarvis

import android.app.Activity
import android.app.AlertDialog
import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.*
import java.util.concurrent.Executors

open class FeatureActivity : Activity() {
    protected lateinit var column: LinearLayout
    protected val worker = Executors.newSingleThreadExecutor()
    protected val ui = Handler(Looper.getMainLooper())
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        column = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; val d=resources.displayMetrics.density; setPadding((18*d).toInt(),(12*d).toInt(),(18*d).toInt(),(24*d).toInt()) }
        val scroll = ScrollView(this).apply { isFillViewport=true; background=Ui.backdrop(); isVerticalScrollBarEnabled=false; addView(column) }
        scroll.setOnApplyWindowInsetsListener { v, insets -> val bars = insets.getInsets(android.view.WindowInsets.Type.systemBars() or android.view.WindowInsets.Type.ime()); v.setPadding(bars.left,bars.top,bars.right,bars.bottom); insets }
        setContentView(scroll)
    }
    protected fun line(text: String) = TextView(this).apply { this.text = text; setTextColor(Ui.TEXT); textSize=14f; setLineSpacing(0f,1.12f); setPadding(px(4),px(8),px(4),px(8)); column.addView(this) }
    protected fun button(text: String, action: () -> Unit) = Button(this).apply { this.text=text; textSize=12f; letterSpacing=.08f; setTextColor(Ui.CYAN); stateListAnimator=null; background=Ui.pill(Ui.GLASS, Ui.LINE, px(14).toFloat()); setOnClickListener { action() }; column.addView(this, LinearLayout.LayoutParams(-1, px(50)).apply { topMargin=px(5); bottomMargin=px(5) }) }
    protected fun field(parent: LinearLayout, hint: String, value: String = "", secret: Boolean = false) = EditText(this).apply {
        this.hint=hint; setText(value); setTextColor(Color.WHITE); setHintTextColor(Ui.MUTED); textSize=14f; background=Ui.pill(Ui.GLASS, Ui.LINE, px(12).toFloat()); setPadding(px(14),px(12),px(14),px(12))
        if(secret) inputType=android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
        parent.addView(this)
    }
    protected fun px(v: Int) = (resources.displayMetrics.density * v).toInt()
    protected fun error(e: Throwable) { AlertDialog.Builder(this).setTitle("JARVIS").setMessage(e.message ?: "Não foi possível concluir.").setPositiveButton("OK",null).show() }
    override fun onDestroy() { worker.shutdownNow(); ui.removeCallbacksAndMessages(null); super.onDestroy() }
}
