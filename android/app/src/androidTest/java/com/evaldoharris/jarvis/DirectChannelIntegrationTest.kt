package com.evaldoharris.jarvis

import android.os.Build
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.MediaType.Companion.toMediaType
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Requires the loopback-only Python direct_fixture, reached through adb reverse. */
@RunWith(AndroidJUnit4::class)
class DirectChannelIntegrationTest {
    @Test fun keystoreDevicePairsWithPythonThenSyncsAndRevocationStopsIt() {
        assumeTrue(Build.FINGERPRINT.contains("generic") || Build.MODEL.contains("sdk"))
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val client = OkHttpClient()
        val ticket = client.newCall(Request.Builder().url("http://127.0.0.1:18888/fixture-ticket").build()).execute().use {
            require(it.isSuccessful); JSONObject(it.body!!.string()).getString("ticket")
        }
        DirectChannel.enroll(context, ticket)
        val cfg = JSONObject(SecureStore(context).get("direct_config"))
        assertTrue(cfg.getString("alias").startsWith("jarvis_direct_"))
        assertFalse(cfg.has("private_key"))
        fun body() = JSONObject().put("device", JSONObject().put("id", cfg.getString("id")).put("name", "Android TLS fixture"))
            .put("updates", JSONArray())
        val result = DirectChannel.sync(context, body())
        assertTrue(result.getBoolean("ok"))
        assertTrue(result.getJSONArray("records").toString().contains("Canal TLS verificado"))
        // New TLS client reloads the persistent Android Keystore identity successfully.
        assertTrue(DirectChannel.sync(context, body()).getBoolean("ok"))
        client.newCall(Request.Builder().url("http://127.0.0.1:18888/fixture-revoke")
            .post(JSONObject().put("id", cfg.getString("id")).toString().toRequestBody("application/json".toMediaType())).build()).execute().close()
        val refused = runCatching { DirectChannel.sync(context, body()) }
        assertTrue(refused.isFailure)
        assertTrue(refused.exceptionOrNull()?.message.orEmpty().contains("HTTP 403"))
        assertEquals("true", SecureStore(context).get("direct_enabled")) // No silent fallback to HTTP.
    }
}
