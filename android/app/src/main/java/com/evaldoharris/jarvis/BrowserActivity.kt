package com.evaldoharris.jarvis

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.os.Bundle
import android.view.Gravity
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import org.json.JSONObject

/** Visible browser owned by the user. No JavaScript-to-native bridge or file access. */
class BrowserActivity : Activity() {
    internal lateinit var web: WebView
    private lateinit var address: EditText
    @Volatile internal var loading = false
    @Volatile internal var failure = ""
    @Volatile internal var foreground = false
    internal var revision = 0L
    private val visited = mutableListOf<String>()
    private var historyIndex = -1
    private var pendingHistoryIndex: Int? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(Color.rgb(3, 12, 19)) }
        root.setOnApplyWindowInsetsListener { v, insets ->
            val bars = insets.getInsets(android.view.WindowInsets.Type.systemBars() or android.view.WindowInsets.Type.ime())
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom); insets
        }
        val bar = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
        bar.addView(Button(this).apply { text = "◉"; contentDescription = "Voltar ao JARVIS"; setOnClickListener { startActivity(Intent(this@BrowserActivity, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)) } }, LinearLayout.LayoutParams(dp(48), dp(48)))
        address = EditText(this).apply { setSingleLine(); hint = "Endereço ou pesquisa"; setTextColor(Color.CYAN); textSize = 13f }
        bar.addView(address, LinearLayout.LayoutParams(0, -2, 1f))
        bar.addView(Button(this).apply { text = "IR"; setOnClickListener {
            runCatching {
                val value = address.text.toString()
                navigate(if (value.contains(' ') || !value.contains('.')) BrowserAddress.search(value) else BrowserAddress.normalize(value))
            }.onFailure { address.error = it.message }
        } }, LinearLayout.LayoutParams(dp(56), dp(48)))
        root.addView(bar)
        web = WebView(this)
        WebView.setWebContentsDebuggingEnabled(false)
        web.settings.apply {
            javaScriptEnabled = true; domStorageEnabled = true
            allowFileAccess = false; allowContentAccess = false
            javaScriptCanOpenWindowsAutomatically = false
            setSupportMultipleWindows(false)
            mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
        }
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean =
                runCatching { BrowserAddress.normalize(request.url.toString()); false }.getOrDefault(true)
            override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) { loading = true; failure = ""; revision++; address.setText(url) }
            override fun onPageFinished(view: WebView, url: String?) {
                if (url != view.url || url == null) return
                val previous = pendingHistoryIndex
                if (previous != null) {
                    historyIndex = previous; visited[previous] = url; pendingHistoryIndex = null
                } else if (historyIndex < 0 || visited[historyIndex] != url) {
                    while (visited.size > historyIndex + 1) visited.removeAt(visited.lastIndex)
                    visited.add(url); historyIndex = visited.lastIndex
                }
                loading = false; address.setText(url)
            }
            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) { failure = "Não foi possível carregar a página (${error.errorCode})."; loading = false }
            }
        }
        root.addView(web, LinearLayout.LayoutParams(-1, 0, 1f)); setContentView(root)
        MobileBrowser.current = this
        intent.getStringExtra("url")?.let { runCatching { navigate(it) } }
    }
    internal fun navigate(url: String) { failure = ""; loading = true; web.loadUrl(BrowserAddress.normalize(url)) }
    internal fun previousPage(): Boolean {
        // Chromium can exclude script-triggered visits from canGoBack(). Keep
        // committed destinations so back still works for assistant navigation.
        if (historyIndex <= 0) return false
        pendingHistoryIndex = historyIndex - 1; loading = true
        if (web.canGoBack()) web.goBack() else web.loadUrl(visited[historyIndex - 1])
        return true
    }
    internal fun history() = JSONObject().put("size", visited.size).put("index", historyIndex)
    internal fun picture(): String {
        check(web.width > 0 && web.height > 0) { "Navegador ainda não está visível." }
        val bitmap = Bitmap.createBitmap(web.width, web.height, Bitmap.Config.ARGB_8888)
        return try { web.draw(Canvas(bitmap)); PhoneTools.encode(bitmap) } finally { bitmap.recycle() }
    }
    internal fun evaluate(script: String, callback: (JSONObject) -> Unit) {
        web.evaluateJavascript("JSON.stringify((function(){ $script })())") { raw ->
            val result = runCatching { JSONObject(org.json.JSONTokener(raw).nextValue().toString()) }
                .getOrElse { PhoneTools.result(false, "A página não permitiu inspecionar o controle.") }
            callback(result)
        }
    }
    override fun onResume() { super.onResume(); foreground = true; MobileBrowser.current = this }
    override fun onPause() { foreground = false; super.onPause() }
    @Deprecated("Deprecated in Java") override fun onBackPressed() { if (!previousPage()) super.onBackPressed() }
    override fun onDestroy() {
        if (MobileBrowser.current === this) MobileBrowser.current = null
        web.stopLoading(); web.destroy(); super.onDestroy()
    }
    private fun dp(value: Int) = (resources.displayMetrics.density * value).toInt()
}
