package com.evaldoharris.jarvis

import android.os.Build
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Opt-in read-only synchronization diagnostic for an already paired device. */
@RunWith(AndroidJUnit4::class)
class DirectConnectionDiagnosticTest {
    @Test fun verifyExistingDeviceConnection() {
        assumeTrue(InstrumentationRegistry.getArguments().getString("jarvisDiagnostics") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val store = SecureStore(context)
        val cfg = JSONObject(store.get("direct_config"))
        Log.i("JarvisDirectCheck", "url=${cfg.optString("url")} local=${cfg.optString("local_url")} external=${cfg.optString("external_url")}")
        val body = JSONObject().put("profile", store.get("shared_profile"))
            .put("device", JSONObject().put("id", cfg.getString("id")).put("name", "${Build.MANUFACTURER} ${Build.MODEL}").put("platform", "Android"))
            .put("updates", JSONArray())
        val repair = InstrumentationRegistry.getArguments().getString("localUrl")
        val previous = store.get("direct_config")
        if (repair != null) {
            val local = ServerAddress.normalize(repair); require(local.startsWith("https://"))
            cfg.put("local_url", local)
            store.put("direct_config", cfg.toString())
        }
        val result = try { DirectChannel.sync(context, body) } catch (error: Exception) {
            if (repair != null) store.put("direct_config", previous)
            throw error
        }
        check(result.has("profile"))
        Log.i("JarvisDirectCheck", "Verified TLS and authenticated synchronization succeeded")
    }
}
