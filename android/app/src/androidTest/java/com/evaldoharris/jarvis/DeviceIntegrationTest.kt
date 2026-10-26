package com.evaldoharris.jarvis

import android.content.Intent
import android.app.UiAutomation
import android.os.ParcelFileDescriptor
import android.provider.Settings
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.Before
import org.junit.runner.RunWith
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class DeviceIntegrationTest {
    @Test fun phoneControlsUseUniqueTextOrResourceIdAndReportBounds() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        SecureStore(context).put("voice_mode", "off")
        val activity = instrumentation.startActivitySync(Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as MainActivity
        val clicked = java.util.concurrent.atomic.AtomicReference("")
        try {
            instrumentation.runOnMainSync {
                val body = android.widget.LinearLayout(activity).apply { orientation = android.widget.LinearLayout.VERTICAL }
                body.addView(android.widget.Button(activity).apply { text = "GOTAB"; id = android.R.id.button1; setOnClickListener { clicked.set("gotab") } })
                body.addView(android.widget.Button(activity).apply { text = "Mae"; id = android.R.id.button2; setOnClickListener { clicked.set("mae") } })
                repeat(2) { body.addView(android.widget.Button(activity).apply { text = "Duplicado" }) }
                activity.setContentView(body)
            }
            waitUntil { JarvisAccessibilityService.current != null && PhoneTools.execute(context, "tree", JSONObject()).optString("visible_text").contains("GOTAB") }
            val tree = PhoneTools.execute(context, "tree", JSONObject())
            assertTrue(tree.getJSONArray("nodes").toString().contains("bounds"))
            assertTrue(PhoneTools.execute(context, "click", JSONObject().put("text", "GOTAB")).getBoolean("ok"))
            assertEquals("gotab", clicked.get())
            assertFalse(PhoneTools.execute(context, "click", JSONObject().put("text", "Duplicado")).getBoolean("ok"))
            assertEquals("gotab", clicked.get())
            assertTrue(PhoneTools.execute(context, "click", JSONObject().put("resource_id", "android:id/button2")).getBoolean("ok"))
            assertEquals("mae", clicked.get())
            assertTrue(PhoneTools.execute(context, "apps", JSONObject()).getJSONArray("apps").length() > 0)
        } finally { instrumentation.runOnMainSync { activity.finish() } }
    }

    @Test fun mobileBrowserObservesTypesAndClicksHotelLinkWithoutConfusingHeading() {
        SecureStore(context).put("voice_mode", "off")
        val server = MockWebServer()
        server.dispatcher = object : okhttp3.mockwebserver.Dispatcher() {
            override fun dispatch(request: okhttp3.mockwebserver.RecordedRequest): MockResponse {
                val html = if (request.path?.startsWith("/hotel") == true) "<html><head><title>Hotel confirmado</title></head><body>Pagina Golden Garden carregada</body></html>" else """
                    <html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Busca teste</title></head><body>
                    <h1>Golden Garden House (Hostel)</h1>
                    <a id="hotel" href="/hotel" target="_blank">Golden Garden Hostel</a>
                    <input id="query" placeholder="Destino" oninput="document.getElementById('echo').textContent=this.value">
                    <p id="echo"></p><input id="password" type="password">
                    <button>Reservar</button><button>Reservar</button>
                    </body></html>
                """.trimIndent()
                return MockResponse().addHeader("Content-Type", "text/html; charset=utf-8").setBody(html)
            }
        }
        server.start()
        try {
            val page = MobileBrowser.execute(context, "open", JSONObject().put("url", server.url("/").toString()))
            assertTrue(page.toString().take(500), page.optBoolean("ok"))
            assertEquals("Busca teste", page.getString("title"))
            assertTrue(page.getString("image").isNotBlank())
            val screenshot = android.util.Base64.decode(page.getString("image"), android.util.Base64.NO_WRAP)
            val bitmap = android.graphics.BitmapFactory.decodeByteArray(screenshot, 0, screenshot.size)
            assertTrue(bitmap.width > 100 && bitmap.height > 100)
            val colors = mutableSetOf<Int>()
            for (y in 0 until minOf(300, bitmap.height) step 3) for (x in 0 until bitmap.width step 3) colors.add(bitmap.getPixel(x, y))
            assertTrue("Captura do navegador não pode estar vazia", colors.size > 10)
            bitmap.recycle()
            java.io.File(context.cacheDir, "qa-browser.jpg").writeBytes(screenshot)
            assertTrue(page.getJSONArray("controls").toString().contains("Golden Garden Hostel"))
            val ambiguous = MobileBrowser.execute(context, "click", JSONObject().put("text", "Reservar"))
            assertFalse(ambiguous.getBoolean("ok")); assertEquals(2, ambiguous.getInt("matches"))
            val value = "Ubatuba '); window.evil=true; //"
            val typed = MobileBrowser.execute(context, "type", JSONObject().put("id", "query").put("value", value))
            assertTrue(typed.getBoolean("ok")); assertTrue(typed.getString("visible_text").contains(value))
            assertFalse(MobileBrowser.execute(context, "type", JSONObject().put("id", "password").put("value", "secret")).getBoolean("ok"))
            val hotel = MobileBrowser.execute(context, "click", JSONObject().put("text", "Golden Garden"))
            assertTrue(hotel.toString().take(500), hotel.optBoolean("ok"))
            assertEquals("Hotel confirmado", hotel.getString("title"))
            assertTrue(hotel.getString("url").endsWith("/hotel"))
            val previous = MobileBrowser.execute(context, "back", JSONObject())
            assertTrue(previous.toString().take(500) + " hotel_history=" + hotel.optJSONObject("history") + " initial_history=" + page.optJSONObject("history"), previous.optBoolean("ok"))
            assertEquals("Busca teste", previous.getString("title"))
            assertFalse(MobileBrowser.execute(context, "open", JSONObject().put("url", "file:///data/data/private")).getBoolean("ok"))
        } finally {
            InstrumentationRegistry.getInstrumentation().runOnMainSync { MobileBrowser.current?.finish() }
            server.shutdown()
        }
    }

    @Test fun continuousMicrophoneKeepsOneStreamAcrossSilenceAndCloses() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val automation = instrumentation.getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES)
        ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand("pm grant ${context.packageName} android.permission.RECORD_AUDIO")).use { it.readBytes() }
        val store = SecureStore(context); store.put("voice_mode", "off")
        val activity = instrumentation.startActivitySync(Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as MainActivity
        val failed = java.util.concurrent.atomic.AtomicBoolean(false)
        val capture = ContinuousMicrophone { true }
        try {
            capture.start { failed.set(true) }
            val reader = java.util.concurrent.Executors.newSingleThreadExecutor()
            try {
                val future = reader.submit<Boolean> {
                    val input = ParcelFileDescriptor.AutoCloseInputStream(capture.source)
                    val buffer = ByteArray(3200)
                    repeat(30) {
                        val count = input.read(buffer)
                        if (count <= 0 || buffer.take(count).any { it != 0.toByte() }) return@submit false
                    }
                    true
                }
                assertTrue(future.get(15, java.util.concurrent.TimeUnit.SECONDS))
                assertFalse(failed.get())
            } finally { capture.close(); reader.shutdownNow() }
        } finally { capture.close(); instrumentation.runOnMainSync { activity.finish() } }
    }

    @Test fun microphoneForegroundServiceCanStartAndStopWithoutCapturingDuringManualPause() {
        org.junit.Assume.assumeTrue(android.speech.SpeechRecognizer.isRecognitionAvailable(context))
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val automation = instrumentation.getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES)
        ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand("pm grant ${context.packageName} android.permission.RECORD_AUDIO")).use { it.readBytes() }
        val store = SecureStore(context); store.put("voice_mode", "off")
        val activity = instrumentation.startActivitySync(Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as MainActivity
        try {
            AppState.manualListening = true
            store.put("voice_mode", "wake")
            instrumentation.runOnMainSync { context.startForegroundService(Intent(context, WakeListeningService::class.java)) }
            waitUntil { AppState.wakeRunning }
            context.stopService(Intent(context, WakeListeningService::class.java))
            waitUntil { !AppState.wakeRunning }
        } finally {
            store.put("voice_mode", "off"); AppState.manualListening = false
            context.stopService(Intent(context, WakeListeningService::class.java))
            instrumentation.runOnMainSync { activity.finish() }
        }
    }

    @Test fun geminiVoiceUsesDesktopVoiceNameAndAudioInsteadOfAndroidTts() {
        val server = MockWebServer()
        val setup = java.util.concurrent.CompletableFuture<JSONObject>()
        server.enqueue(MockResponse().withWebSocketUpgrade(object : okhttp3.WebSocketListener() {
            override fun onMessage(socket: okhttp3.WebSocket, text: String) {
                val message = JSONObject(text)
                if (message.has("setup")) {
                    setup.complete(message.getJSONObject("setup"))
                    socket.send("{\"setupComplete\":{}}")
                } else if (message.has("clientContent")) {
                    assertTrue(message.getJSONObject("clientContent").getBoolean("turnComplete"))
                    val silence = android.util.Base64.encodeToString(ByteArray(4800), android.util.Base64.NO_WRAP)
                    socket.send("""{"serverContent":{"modelTurn":{"parts":[{"inlineData":{"mimeType":"audio/pcm;rate=24000","data":"$silence"}}]},"turnComplete":true}}""")
                }
            }
            override fun onClosing(socket: okhttp3.WebSocket, code: Int, reason: String) { socket.close(code, null) }
        }))
        val store = SecureStore(context)
        store.put("gemini_key", "test-key"); store.put("speak", "true"); store.put("voice_name", "Charon")
        server.start()
        try {
            GeminiVoice.speak(context, "Teste da voz.", server.url("/live").toString().replaceFirst("http", "ws"))
            val config = setup.get(5, TimeUnit.SECONDS)
            assertEquals("Charon", config.getJSONObject("generationConfig").getJSONObject("speechConfig").getJSONObject("voiceConfig").getJSONObject("prebuiltVoiceConfig").getString("voiceName"))
            waitUntil { !AppState.audioBusy }
        } finally { GeminiVoice.stop(); server.shutdown(); store.put("gemini_key", "") }
    }

    @Test fun reactorRemainsVisibleWhenConversationScrolls() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        SecureStore(context).put("voice_mode", "off")
        val activity = instrumentation.startActivitySync(Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as MainActivity
        try {
            repeat(12) { AppState.message("TEST", "Linha de histórico ".repeat(60)) }
            instrumentation.waitForIdleSync()
            val before = android.graphics.Rect(); val after = android.graphics.Rect()
            instrumentation.runOnMainSync {
                val reactor = activity.findViewById<android.view.View>(R.id.reactor)
                assertTrue(reactor.getGlobalVisibleRect(before))
                activity.findViewById<android.widget.ScrollView>(R.id.conversation_scroll).fullScroll(android.view.View.FOCUS_DOWN)
            }
            instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync { assertTrue(activity.findViewById<android.view.View>(R.id.reactor).getGlobalVisibleRect(after)); assertEquals(before.top, after.top); assertEquals(before.height(), after.height()) }
        } finally { instrumentation.runOnMainSync { activity.finish() } }
    }

    @Test fun overloadRetriesAreBoundedAndCanBeCancelled() {
        val server = MockWebServer()
        repeat(4) { server.enqueue(MockResponse().setResponseCode(503).setBody("""{"error":{"message":"high demand"}}""")) }
        server.start()
        try {
            val endpoint = server.url("/").toString().trimEnd('/')
            try { GeminiApi(endpoint).generate("test-key", "gemini-current-flash", JSONObject()) {}; fail("Expected overload error") }
            catch (error: IllegalStateException) { assertTrue(error.message!!.contains("sobrecarregado")) }
            assertEquals(3, server.requestCount)
            var stopped = false
            try {
                GeminiApi(endpoint, cancelled = { stopped }, onRetry = { stopped = true })
                    .generate("test-key", "gemini-current-flash", JSONObject()) {}
                fail("Expected cancellation")
            } catch (error: IllegalStateException) { assertTrue(error.message!!.contains("interrompido")) }
            assertEquals(4, server.requestCount)
        } finally { server.shutdown() }
    }

    @Test fun overloadedModelRetriesTwiceAndThenSucceedsWithoutSwitchingModel() {
        val server = MockWebServer()
        repeat(2) { server.enqueue(MockResponse().setResponseCode(503).setBody("""{"error":{"message":"high demand"}}""")) }
        server.enqueue(MockResponse().setBody("""{"candidates":[{"content":{"role":"model","parts":[{"text":"ok"}]}}]}"""))
        server.start()
        try {
            val retries = mutableListOf<Int>()
            val api = GeminiApi(server.url("/").toString().trimEnd('/'), onRetry = { retries.add(it) })
            var switched = false
            val response = api.generate("test-key", "gemini-current-flash-lite", JSONObject()) { switched = true }
            assertTrue(response.has("candidates"))
            assertEquals(listOf(1, 2), retries)
            assertFalse(switched)
            assertEquals(3, server.requestCount)
            repeat(3) { assertTrue(server.takeRequest(2, TimeUnit.SECONDS)!!.path!!.contains("gemini-current-flash-lite:generateContent")) }
        } finally { server.shutdown() }
    }

    @Test fun missingModelDiscoversSupportedAlternativeAndNeverRetriesQuota() {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(404).setBody("""{"error":{"message":"old model not found"}}"""))
        server.enqueue(MockResponse().setBody("""{"models":[{"name":"models/gemini-new-flash","supportedGenerationMethods":["generateContent"]},{"name":"models/gemini-image-model","supportedGenerationMethods":["generateContent"]}]}"""))
        server.enqueue(MockResponse().setBody("""{"candidates":[{"content":{"role":"model","parts":[{"text":"ok"}]}}]}"""))
        server.enqueue(MockResponse().setResponseCode(429).setBody("""{"error":{"message":"quota test-key exhausted"}}"""))
        server.start()
        try {
            val api = GeminiApi(server.url("/").toString().trimEnd('/'))
            var selected = ""
            api.generate("test-key", "gemini-old-flash", JSONObject()) { selected = it }
            assertEquals("gemini-new-flash", selected)
            assertTrue(server.takeRequest(2, TimeUnit.SECONDS)!!.path!!.contains("gemini-old-flash:generateContent"))
            assertTrue(server.takeRequest(2, TimeUnit.SECONDS)!!.path!!.startsWith("/v1beta/models?"))
            assertTrue(server.takeRequest(2, TimeUnit.SECONDS)!!.path!!.contains("gemini-new-flash:generateContent"))
            try { api.generate("test-key", "gemini-new-flash", JSONObject()) {}; fail("Expected quota error") }
            catch (error: IllegalStateException) { assertTrue(error.message!!.contains("cota")); assertFalse(error.message!!.contains("test-key")) }
            assertEquals(4, server.requestCount)
        } finally { server.shutdown() }
    }

    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private fun waitUntil(timeout: Long = 15000, predicate: () -> Boolean) {
        val end = System.currentTimeMillis() + timeout
        while (!predicate() && System.currentTimeMillis() < end) Thread.sleep(100)
        assertTrue("Condition did not become true", predicate())
    }

    @Before fun keepAccessibilityEnabledInInstrumentation() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val automation = instrumentation.getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES)
        if (JarvisAccessibilityService.current == null) {
            val component = "${context.packageName}/${JarvisAccessibilityService::class.java.name}"
            val services = Settings.Secure.getString(context.contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES).orEmpty()
                .split(':').filter { it.isNotBlank() && !it.startsWith(context.packageName + "/") }
            fun shell(command: String) { ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand(command)).use { it.readBytes() } }
            if (services.isEmpty()) shell("settings delete secure enabled_accessibility_services")
            else shell("settings put secure enabled_accessibility_services ${services.joinToString(":")}")
            shell("settings put secure enabled_accessibility_services ${(services + component).joinToString(":")}")
            shell("settings put secure accessibility_enabled 1")
        }
    }

    @Test fun keystoreRoundTripAndAccessibilityScreen() {
        val store = SecureStore(context)
        store.put("integration_secret", "private test value")
        assertEquals("private test value", SecureStore(context).get("integration_secret"))
        val raw = context.getSharedPreferences("jarvis_private", 0).getString("integration_secret", "")!!
        assertFalse(raw.contains("private test value"))
        waitUntil { JarvisAccessibilityService.current != null }
        val status = PhoneTools.execute(context, "status", JSONObject())
        assertTrue(status.getBoolean("accessibility"))
        val screenshot = PhoneTools.execute(context, "screen", JSONObject())
        assertTrue(screenshot.toString().take(200), screenshot.getBoolean("ok"))
        assertTrue(screenshot.getString("image").startsWith("/9j/"))
        assertFalse(PhoneTools.execute(context, "tap", JSONObject().put("x", 2).put("y", .5)).getBoolean("ok"))
    }

    @Test fun independentAgentUsesFunctionResultAndPreservesThoughtSignature() {
        val store = SecureStore(context)
        store.put("gemini_key", "test-key-not-real")
        val server = MockWebServer()
        server.enqueue(MockResponse().setBody("""{"candidates":[{"content":{"role":"model","parts":[{"thoughtSignature":"test-signature","functionCall":{"name":"phone","args":{"action":"status"}}}]}}]}"""))
        server.enqueue(MockResponse().setBody("""{"candidates":[{"content":{"role":"model","parts":[{"text":"Assistente Android independente funcionando."}]}}]}"""))
        server.start()
        try {
            val assistant = JarvisAssistant(context, server.url("/").toString().trimEnd('/'), prepareVoice = {})
            assistant.ask("Confira o estado do celular sem usar o PC.")
            waitUntil { AppState.transcript().contains("Assistente Android independente funcionando.") }
            assertEquals("test-key-not-real", server.takeRequest(5, TimeUnit.SECONDS)!!.getHeader("x-goog-api-key"))
            val request = server.takeRequest(5, TimeUnit.SECONDS)!!.body.readUtf8()
            assertTrue(request.contains("test-signature"))
            assertTrue(request.contains("functionResponse"))
            assertTrue(request.contains("accessibility"))
        } finally { server.shutdown(); store.put("gemini_key", "") }
    }

    @Test fun pairWithFixturePcAndReceiveRemoteControl() {
        val args = InstrumentationRegistry.getArguments()
        val pin = args.getString("pcPin") ?: return
        val store = SecureStore(context)
        store.put("pc_url", "http://10.0.2.2:8771")
        PcClient(context).pair(pin)
        PcClient(context).command("Teste de integração Android para PC; não executar ações reais.")
        store.put("remote_enabled", "true")
        context.startForegroundService(Intent(context, PhoneControlService::class.java))
        waitUntil { AppState.connection.contains("PC conectado") }
        waitUntil(25000) { AppState.transcript().contains("Resposta de teste entregue ao Android.") }
        store.put("remote_enabled", "false")
        context.stopService(Intent(context, PhoneControlService::class.java))
    }
}
