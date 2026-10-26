package com.evaldoharris.jarvis

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class LatencyIntegrationTest {
    private val context get()=InstrumentationRegistry.getInstrumentation().targetContext
    private fun waitUntil(test:()->Boolean){val until=System.currentTimeMillis()+15000;while(!test()&&System.currentTimeMillis()<until)Thread.sleep(25);assertTrue(test())}
    @Test fun oldToolImagesAreNotResentButUserPhotoAndThoughtSignatureStay(){
        val user=JSONObject("""{"role":"user","parts":[{"text":"Veja minha foto"},{"inlineData":{"mimeType":"image/jpeg","data":"USER_PHOTO"}}]}""")
        val model=JSONObject("""{"role":"model","parts":[{"thoughtSignature":"private-signature","functionCall":{"name":"phone","args":{"action":"screen"}}}]}""")
        fun observation(image:String)=JSONObject().put("role","user").put("parts",JSONArray().put(JSONObject().put("functionResponse",JSONObject().put("name","phone").put("response",JSONObject().put("ok",true))))
            .put(JSONObject().put("inlineData",JSONObject().put("mimeType","image/jpeg").put("data",image))))
        val old=observation("OLD_FRAME");val newest=observation("CURRENT_FRAME")
        val request=AgentHistory.contents(listOf(user,model,old,newest)).toString()
        assertFalse(request.contains("OLD_FRAME"));assertTrue(request.contains("CURRENT_FRAME"));assertTrue(request.contains("USER_PHOTO"));assertTrue(request.contains("private-signature"))
        assertTrue(old.toString().contains("OLD_FRAME"));assertEquals(model.toString(),AgentHistory.contents(listOf(user,model,old,newest)).getJSONObject(1).toString())
    }
    @Test fun preparedVoiceReusesConnectionAndDoesNotSpeakBeforeAnswer(){
        val server=MockWebServer();val setup=CompletableFuture<JSONObject>();val text=CompletableFuture<String>()
        server.enqueue(MockResponse().withWebSocketUpgrade(object:WebSocketListener(){
            override fun onMessage(ws:WebSocket,raw:String){
                val message=JSONObject(raw)
                if(message.has("setup")){setup.complete(message.getJSONObject("setup"));ws.send("{\"setupComplete\":{}}")}else if(message.has("clientContent")){
                    text.complete(message.getJSONObject("clientContent").getJSONArray("turns").getJSONObject(0).getJSONArray("parts").getJSONObject(0).getString("text"))
                    val pcm=android.util.Base64.encodeToString(ByteArray(4800),android.util.Base64.NO_WRAP)
                    ws.send("""{"serverContent":{"modelTurn":{"parts":[{"inlineData":{"mimeType":"audio/pcm;rate=24000","data":"$pcm"}}]},"turnComplete":true}}""")
                }
            }
            override fun onClosing(ws:WebSocket,code:Int,reason:String){ws.close(code,null)}
        }))
        val store=SecureStore(context);val keys=listOf("gemini_key","voice_name","speak");val old=keys.associateWith{store.get(it)}
        server.start();val endpoint=server.url("/live").toString().replaceFirst("http","ws")
        try{
            store.put("gemini_key","fake-key");store.put("voice_name","Charon");store.put("speak","true");GeminiVoice.stop()
            GeminiVoice.prepare(context,endpoint)
            val voice=setup.get(5,TimeUnit.SECONDS).getJSONObject("generationConfig").getJSONObject("speechConfig").getJSONObject("voiceConfig").getJSONObject("prebuiltVoiceConfig").getString("voiceName")
            assertEquals("Charon",voice);assertFalse(text.isDone);assertFalse(AppState.audioBusy)
            GeminiVoice.speak(context,"Ação confirmada.",endpoint)
            assertEquals("Ação confirmada.",text.get(5,TimeUnit.SECONDS));waitUntil{!AppState.audioBusy}
            assertEquals(1,server.requestCount)
        }finally{GeminiVoice.stop();server.shutdown();old.forEach{(key,value)->store.put(key,value)}}
    }
    @Test fun multipleReadOnlyToolsDoNotAccumulateFixedHalfSecondPauses(){
        val server=MockWebServer();val store=SecureStore(context);val oldKey=store.get("gemini_key")
        val calls=JSONArray();repeat(6){calls.put(JSONObject().put("functionCall",JSONObject().put("name","phone").put("args",JSONObject().put("action","status"))))}
        server.enqueue(MockResponse().setBody(JSONObject().put("candidates",JSONArray().put(JSONObject().put("content",JSONObject().put("role","model").put("parts",calls)))).toString()))
        server.enqueue(MockResponse().setBody("""{"candidates":[{"content":{"role":"model","parts":[{"text":"Verificação rápida concluída."}]}}]}"""))
        server.start();store.put("gemini_key","fake-key")
        try{
            val started=android.os.SystemClock.elapsedRealtime()
            val assistant=JarvisAssistant(context,server.url("/").toString().trimEnd('/'),prepareVoice={})
            assistant.ask("Verifique o estado do celular.")
            waitUntil{AppState.transcript().contains("Verificação rápida concluída.")}
            android.util.Log.d("JarvisLatency","six_tools_mock_ms=${android.os.SystemClock.elapsedRealtime()-started}")
            server.takeRequest(5,TimeUnit.SECONDS)
            val response=JSONObject(server.takeRequest(5,TimeUnit.SECONDS)!!.body.readUtf8()).getJSONArray("contents").getJSONObject(2).getJSONArray("parts")
            assertEquals(6,response.length());assertEquals(2,server.requestCount)
        }finally{server.shutdown();store.put("gemini_key",oldKey)}
    }
}
