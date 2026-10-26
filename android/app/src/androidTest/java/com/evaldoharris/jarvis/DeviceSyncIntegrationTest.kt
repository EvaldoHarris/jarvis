package com.evaldoharris.jarvis

import android.os.Build
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class DeviceSyncIntegrationTest {
    @Test fun phoneSharesOfflineMemoryTasksAndContextWithoutRunningActions() {
        // This fixture deliberately changes settings; never run against a person's real phone.
        assumeTrue(Build.FINGERPRINT.contains("generic") || Build.MODEL.contains("sdk"))
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val store = SecureStore(context)
        store.put("direct_enabled", "false")
        val server = MockWebServer()
        val records = linkedMapOf<String, JSONObject>()
        var revision = 1L
        records["memory|identity:name"] = JSONObject().put("kind", "memory").put("key", "identity:name").put("revision", revision)
            .put("value", JSONObject().put("category", "identity").put("key", "name").put("value", "Pessoa de teste"))
        records["task|pc-task"] = JSONObject().put("kind", "task").put("key", "pc-task").put("revision", ++revision)
            .put("value", JSONObject().put("id", "pc-task").put("title", "Tarefa do PC").put("done", false).put("due_ms", 0))
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                if (request.path != "/api/continuity/sync" || request.getHeader("Authorization") != "Bearer fixture") return MockResponse().setResponseCode(401)
                val body = JSONObject(request.body.readUtf8())
                val result = JSONArray()
                synchronized(records) {
                    val updates = body.getJSONArray("updates")
                    for (i in 0 until updates.length()) {
                        val row = updates.getJSONObject(i)
                        val key = row.getString("kind") + "|" + row.getString("key")
                        val conflict = row.getLong("base") != (records[key]?.optLong("revision") ?: 0L)
                        if (!conflict) records[key] = JSONObject(row.toString()).put("revision", ++revision)
                        result.put(JSONObject().put("id", row.getString("id")).put("conflict", conflict))
                    }
                    return MockResponse().setHeader("Content-Type", "application/json").setBody(JSONObject().put("ok", true).put("profile", "test-profile")
                        .put("results", result).put("records", JSONArray(records.values.toList())).put("devices", JSONArray()).toString())
                }
            }
        }
        server.start()
        try {
            store.put("pc_url", server.url("/").toString().trimEnd('/')); store.put("pc_token", "fixture"); store.put("pc_device_token", "fixture")
            store.put("shared_enabled", "true"); store.put("shared_profile", "")
            for (key in listOf("shared_records", "shared_pending", "shared_bridge")) store.put(key, "{}")
            PersonalData.write(context, "memories", JSONArray().put(JSONObject().put("key", "phone_fact").put("value", "Criado offline no celular")))
            PersonalData.write(context, "tasks", JSONArray())
            DeviceSync.start(context)
            waitUntil { store.get("shared_profile") == "test-profile" }
            assertTrue(PersonalData.read(context, "memories").toString().contains("Pessoa de teste"))
            synchronized(records) { assertTrue(records.containsKey("memory|notes:phone_fact")) }
            assertTrue(PersonalData.read(context, "tasks").toString().contains("Tarefa do PC"))
            PersonalData.tasks(context, "complete", JSONObject().put("id", "pc-task")); DeviceSync.syncSoon()
            waitUntil { synchronized(records) { records["task|pc-task"]!!.getJSONObject("value").optBoolean("done") } }
            DeviceSync.rememberTurn("user", "Continuar a conversa do PC")
            waitUntil { synchronized(records) { records.values.any { it.optString("kind") == "turn" } } }
            assertTrue(DeviceSync.context().contains("Continuar a conversa do PC"))
            assertTrue(DeviceSync.context().contains("nunca repita ações"))
            synchronized(records) {
                records["memory|notes:phone_fact"]!!.put("revision", ++revision).getJSONObject("value").put("value", "Alterado no PC")
            }
            PersonalData.memory(context, "remember", JSONObject().put("key", "phone_fact").put("value", "Alterado no celular"))
            DeviceSync.syncSoon()
            waitUntil { DeviceSync.conflicts().length() == 1 }
            assertTrue(DeviceSync.conflicts().getJSONObject(0).getJSONObject("hub_value").getString("value").contains("Alterado no PC"))
            assertTrue(PersonalData.read(context, "memories").toString().contains("Alterado no celular"))
            DeviceSync.resolve("memory", "notes:phone_fact", false)
            waitUntil { PersonalData.read(context, "memories").toString().contains("Alterado no PC") }
            assertEquals(0, DeviceSync.conflicts().length())
        } finally { server.shutdown() }
    }
    private fun waitUntil(check: () -> Boolean) {
        val deadline = System.currentTimeMillis() + 12000
        while (System.currentTimeMillis() < deadline) { if (check()) return; Thread.sleep(80) }
        assertTrue("Sincronização não concluiu: " + DeviceSync.status, check())
    }
}
