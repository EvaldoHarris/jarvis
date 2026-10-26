package com.evaldoharris.jarvis

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Path
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.view.Display
import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit

object PhoneTools {
    private val main = Handler(Looper.getMainLooper())
    private data class Frame(val id: String, val width: Int, val height: Int, val pkg: String, val window: Int, val signature: Int, val time: Long)
    private var frame: Frame? = null
    private data class Tree(val token: String, val pkg: String, val window: Int, val signature: Int, val time: Long)
    private var tree: Tree? = null
    private fun screenSignature(root: AccessibilityNodeInfo?): Int {
        if (root == null) return 0
        var visited = 0
        fun visit(node: AccessibilityNodeInfo): Int {
            if (++visited > 500 || !node.isVisibleToUser) return 0
            val bounds = android.graphics.Rect().apply { node.getBoundsInScreen(this) }
            var hash = listOf(node.viewIdResourceName, node.className?.toString(), node.text?.toString(), node.contentDescription?.toString(), bounds.toShortString(), node.isEnabled).hashCode()
            for (i in 0 until node.childCount) node.getChild(i)?.let { child ->
                try { hash = 31 * hash + visit(child) } finally { child.recycle() }
            }
            return hash
        }
        return visit(root)
    }
    fun result(ok: Boolean, error: String = ""): JSONObject = JSONObject().put("ok", ok).apply { if (error.isNotEmpty()) put("error", error) }
    fun execute(context: Context, action: String, args: JSONObject): JSONObject {
        if (action == "status") return result(true).put("accessibility", JarvisAccessibilityService.current != null)
            .put("browser", "native_dom_and_vision").put("wake_listening", AppState.wakeRunning).put("pc_connected", AppState.pcReady)
        if (action == "apps") {
            val query = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
            val apps = context.packageManager.queryIntentActivities(query, 0).map {
                it.loadLabel(context.packageManager).toString() to it.activityInfo.packageName
            }.distinct().sortedBy { it.first.lowercase() }
            return result(true).put("apps", JSONArray().apply { apps.take(250).forEach { put(JSONObject().put("name", it.first).put("package", it.second)) } })
        }
        if (action == "open_app") return launchApp(context, args.optString("app"))
        val service = JarvisAccessibilityService.current ?: return result(false, "Ative JARVIS em Configurações → Acessibilidade.")
        val future = CompletableFuture<JSONObject>()
        main.post {
            try {
                when (action) {
                    "screen" -> {
                        val observedRoot = service.rootInActiveWindow
                        val observedPackage = observedRoot?.packageName?.toString().orEmpty()
                        val observedWindow = observedRoot?.windowId ?: -1
                        val observedSignature = screenSignature(observedRoot)
                        observedRoot?.recycle()
                        service.takeScreenshot(Display.DEFAULT_DISPLAY, context.mainExecutor,
                        object : AccessibilityService.TakeScreenshotCallback {
                            override fun onSuccess(value: AccessibilityService.ScreenshotResult) {
                                try {
                                    val hardware = Bitmap.wrapHardwareBuffer(value.hardwareBuffer, value.colorSpace)
                                    value.hardwareBuffer.close()
                                    if (hardware == null) { future.complete(result(false, "Captura indisponível.")); return }
                                    val bitmap = hardware.copy(Bitmap.Config.ARGB_8888, false)
                                    hardware.recycle()
                                    val current = Frame(java.util.UUID.randomUUID().toString().take(8),bitmap.width, bitmap.height, observedPackage, observedWindow, observedSignature, android.os.SystemClock.elapsedRealtime())
                                    frame = current
                                    val encoded = encode(bitmap); bitmap.recycle()
                                    future.complete(result(true).put("image", encoded).put("mime_type", "image/jpeg").put("observation_id", current.id).put("package", current.pkg).put("screen_width", current.width).put("screen_height", current.height))
                                } catch (_: Exception) { future.complete(result(false, "Não foi possível ler a captura.")) }
                            }
                            override fun onFailure(errorCode: Int) { future.complete(result(false, "Captura bloqueada ou indisponível (código $errorCode).")) }
                        })
                    }
                    "back", "home", "recents", "notifications" -> future.complete(result(service.performGlobalAction(when (action) {
                        "back" -> AccessibilityService.GLOBAL_ACTION_BACK
                        "home" -> AccessibilityService.GLOBAL_ACTION_HOME
                        "recents" -> AccessibilityService.GLOBAL_ACTION_RECENTS
                        else -> AccessibilityService.GLOBAL_ACTION_NOTIFICATIONS
                    })))
                    "click", "long_click", "text", "tree", "scroll" -> {
                        val root = service.rootInActiveWindow
                        if (root == null) future.complete(result(false, "Não há janela acessível."))
                        else {
                            try { future.complete(nodeAction(root, action, args)) }
                            finally { root.recycle() }
                        }
                    }
                    "tap", "swipe", "long_press" -> {
                        fun coordinate(key: String): Float {
                            val n = args.optDouble(key, Double.NaN)
                            require(n.isFinite() && n in 0.0..1.0) { "Coordenada deve estar entre 0 e 1." }
                            return n.toFloat()
                        }
                        val observed = frame ?: error("Observe screen antes do gesto.")
                        // A IA às vezes copia o id errado; a captura mais recente e recente ainda vale.
                        if (args.optString("observation_id").trim() != observed.id) android.util.Log.w("JarvisPhone", "observation_id ausente ou diferente; usando a captura mais recente")
                        require(android.os.SystemClock.elapsedRealtime() - observed.time < 15000) { "Captura expirada; observe novamente." }
                        val currentRoot = service.rootInActiveWindow ?: error("Janela indisponível.")
                        try {
                            require(currentRoot.packageName?.toString() == observed.pkg && currentRoot.windowId == observed.window) { "Outro aplicativo ou janela está aberto agora; observe novamente antes do gesto." }
                            // Deslizar não mira um elemento; em apps de vídeo a tela muda o tempo todo.
                            if (action != "swipe") require(screenSignature(currentRoot) == observed.signature) { "A tela mudou; observe novamente antes do gesto." }
                        } finally { currentRoot.recycle() }
                        frame = null
                        val path = Path().apply {
                            moveTo(coordinate("x") * (observed.width - 1), coordinate("y") * (observed.height - 1))
                            if (action == "swipe") lineTo(coordinate("x2") * (observed.width - 1), coordinate("y2") * (observed.height - 1))
                        }
                        val gesture = GestureDescription.Builder().addStroke(GestureDescription.StrokeDescription(path, 0, when(action) { "tap" -> 80; "long_press" -> 800; else -> 400 })).build()
                        val accepted = service.dispatchGesture(gesture, object : AccessibilityService.GestureResultCallback() {
                            override fun onCompleted(gestureDescription: GestureDescription) { future.complete(result(true).put("gesture_completed", true)) }
                            override fun onCancelled(gestureDescription: GestureDescription) { future.complete(result(false, "Gesto cancelado pelo Android.")) }
                        }, main)
                        if (!accepted) future.complete(result(false, "Android recusou o gesto."))
                    }
                    else -> future.complete(result(false, "Ação não suportada."))
                }
            } catch (e: Exception) { future.complete(result(false, e.message ?: "Falha no controle.")) }
        }
        return try { future.get(8, TimeUnit.SECONDS) } catch (_: Exception) { result(false, "Android não confirmou o resultado a tempo.") }
    }

    fun encode(bitmap: Bitmap): String {
        val scale = minOf(1f, 1080f / bitmap.width, 1080f / bitmap.height)
        val small = Bitmap.createScaledBitmap(bitmap, (bitmap.width * scale).toInt().coerceAtLeast(1), (bitmap.height * scale).toInt().coerceAtLeast(1), true)
        val stream = ByteArrayOutputStream(); small.compress(Bitmap.CompressFormat.JPEG, 78, stream)
        if (small !== bitmap) small.recycle()
        return Base64.encodeToString(stream.toByteArray(), Base64.NO_WRAP)
    }

    private fun nodeAction(root: AccessibilityNodeInfo, action: String, args: JSONObject): JSONObject {
        val text = args.optString("text")
        val resourceId = args.optString("resource_id")
        val expectedPackage = args.optString("package")
        if (action != "tree" && expectedPackage.isNotBlank() && root.packageName?.toString() != expectedPackage)
            return result(false, "O aplicativo em primeiro plano mudou; observe novamente.")
        if (action == "text") {
            require(text.length <= 10000) { "Texto muito longo." }
            val focused = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT) ?: return result(false, "Selecione primeiro um campo de texto.")
            return try {
                if (focused.isPassword) result(false, "Digite a senha pessoalmente.")
                else result(focused.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, Bundle().apply { putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text) }))
            } finally { focused.recycle() }
        }
        val elementId = args.optString("element_id")
        val observedTree = tree
        if (elementId.isNotBlank()) {
            tree = null
            require(observedTree != null && elementId.startsWith(observedTree.token + ":") &&
                android.os.SystemClock.elapsedRealtime() - observedTree.time < 30000 &&
                root.windowId == observedTree.window && root.packageName?.toString() == observedTree.pkg &&
                screenSignature(root) == observedTree.signature) { "Controle expirado ou tela alterada; observe tree novamente." }
        }
        val token = java.util.UUID.randomUUID().toString()
        val labels = JSONArray()
        val nodes = JSONArray()
        val matches = mutableListOf<AccessibilityNodeInfo>()
        var visited = 0
        fun visit(node: AccessibilityNodeInfo, path: String) {
            if (++visited > 500) return
            val label = (node.text ?: node.contentDescription)?.toString().orEmpty()
            if (node.isVisibleToUser && !node.isPassword) {
                val bounds = android.graphics.Rect().apply { node.getBoundsInScreen(this) }
                if (nodes.length() < 160 && (label.isNotBlank() || node.isClickable || node.isEditable || node.isScrollable)) nodes.put(JSONObject()
                    .put("element_id", "$token:$path").put("text", label.take(180)).put("resource_id", node.viewIdResourceName ?: "")
                    .put("class", node.className).put("clickable", node.isClickable).put("editable", node.isEditable)
                    .put("scrollable", node.isScrollable).put("enabled", node.isEnabled)
                    .put("bounds", JSONArray(listOf(bounds.left, bounds.top, bounds.right, bounds.bottom))))
                val matchesId = resourceId.isNotBlank() && node.viewIdResourceName == resourceId
                val matchesText = text.isNotBlank() && label.equals(text, ignoreCase = true)
                val target = if (elementId.isNotBlank()) elementId == "${observedTree?.token}:$path" else if (resourceId.isNotBlank()) matchesId && (text.isBlank() || matchesText) else matchesText
                if (action in listOf("click", "long_click") && target) matches.add(AccessibilityNodeInfo.obtain(node))
                if (action == "scroll" && node.isScrollable && (if (text.isBlank() && resourceId.isBlank() && elementId.isBlank()) true else target)) matches.add(AccessibilityNodeInfo.obtain(node))
            }
            if (node.isVisibleToUser && !node.isPassword && label.isNotBlank()) {
                if (labels.length() < 120) labels.put(label.take(180))
            }
            for (i in 0 until node.childCount) node.getChild(i)?.let { child -> try { visit(child, "$path.$i") } finally { child.recycle() } }
        }
        visit(root, "0")
        if (action == "tree") {
            tree = Tree(token, root.packageName?.toString().orEmpty(), root.windowId, screenSignature(root), android.os.SystemClock.elapsedRealtime())
            return result(true).put("visible_text", labels).put("nodes", nodes).put("package", root.packageName)
        }
        try {
            if (matches.size != 1) return result(false, "Texto ausente ou ambíguo; veja a tela antes de escolher outro alvo.")
            if (action == "scroll") {
                val direction = args.optString("direction", "down")
                require(direction in listOf("up", "down")) { "Direção deve ser up ou down." }
                return result(matches[0].performAction(if (direction == "up") AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD else AccessibilityNodeInfo.ACTION_SCROLL_FORWARD))
            }
            var target: AccessibilityNodeInfo? = AccessibilityNodeInfo.obtain(matches[0])
            repeat(6) {
                val node = target ?: return result(false, "Controle não clicável.")
                if ((action == "click" && node.isClickable) || (action == "long_click" && node.isLongClickable)) {
                    val ok = node.isEnabled && node.performAction(if (action == "long_click") AccessibilityNodeInfo.ACTION_LONG_CLICK else AccessibilityNodeInfo.ACTION_CLICK)
                    node.recycle(); return result(ok).put("verified_screen", false)
                }
                target = node.parent; node.recycle()
            }
            target?.recycle()
            return result(false, "Controle não clicável.")
        } finally { matches.forEach { it.recycle() } }
    }

    private fun launchApp(context: Context, name: String): JSONObject {
        if (name.isBlank()) return result(false, "Informe o nome do aplicativo.")
        val future = CompletableFuture<JSONObject>()
        main.post {
            try {
                val pm = context.packageManager
                val query = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
                val options = pm.queryIntentActivities(query, 0).map { it.loadLabel(pm).toString() to it.activityInfo }
                    .distinctBy { it.second.packageName }
                val pick = AppMatcher.best(name, options.map { it.first to it.second.packageName })
                android.util.Log.d("JarvisPhone", "open_app '$name' -> ${pick?.first} (${options.size} apps)")
                if (pick == null) {
                    future.complete(result(false, "Não encontrei um aplicativo chamado '$name'.")
                        .put("suggestions", org.json.JSONArray(AppMatcher.suggestions(name, options.map { it.first }))))
                } else {
                    val info = options.first { it.second.packageName == pick.second }.second
                    // O serviço de acessibilidade pode abrir apps mesmo com o JARVIS em segundo plano.
                    val launcher = JarvisAccessibilityService.current ?: context
                    launcher.startActivity(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER).setClassName(info.packageName, info.name)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED))
                    future.complete(result(true).put("launched", info.packageName).put("label", pick.first).put("verified_screen", false))
                }
            } catch (e: Exception) {
                android.util.Log.w("JarvisPhone", "open_app failed", e)
                future.complete(result(false, "Android não permitiu abrir o aplicativo."))
            }
        }
        return future.get(5, TimeUnit.SECONDS)
    }
}
