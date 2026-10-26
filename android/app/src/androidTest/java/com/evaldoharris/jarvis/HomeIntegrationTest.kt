package com.evaldoharris.jarvis

import android.app.NotificationManager
import android.app.UiAutomation
import android.content.Intent
import android.os.ParcelFileDescriptor
import androidx.core.content.FileProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.time.OffsetDateTime
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class HomeIntegrationTest {
    private val context get()=InstrumentationRegistry.getInstrumentation().targetContext
    @Test fun configuredDvrLivePlaybackAndSnapshot(){
        val token=InstrumentationRegistry.getArguments().getString("homeFixtureToken")?:return
        val store=SecureStore(context)
        val keys=listOf("home_cameras","tuya_key","tuya_secret","tuya_region","pc_url","pc_token","voice_mode")
        val previous=keys.associateWith{store.get(it)}
        val instrumentation=InstrumentationRegistry.getInstrumentation()
        store.put("voice_mode","off")
        val activity=instrumentation.startActivitySync(Intent(context,MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as MainActivity
        try{
            store.put("pc_url","http://10.0.2.2:8771");store.put("pc_token",token)
            HomeConfig.importPc(context,PcClient(context).pairedPost("/api/android/home-config"))
            val camera=CameraTools.selected(context,"intelbras")
            val opened=CameraTools.execute(context,"open",JSONObject().put("name",camera.getString("id")).put("channel",12))
            assertTrue(opened.toString(),opened.optBoolean("playing"))
            val image=CameraTools.execute(context,"snapshot",JSONObject())
            assertTrue(image.optBoolean("ok"));assertTrue(image.getString("image").length>1000)
        }finally{
            CameraTools.execute(context,"stop",JSONObject())
            previous.forEach{(key,value)->store.put(key,value)}
            instrumentation.runOnMainSync{activity.finish()}
        }
    }
    @Test fun featureScreensOpenWithoutNetworkOrAiCalls(){
        val instrumentation=InstrumentationRegistry.getInstrumentation()
        for((type,name) in listOf(HomeActivity::class.java to "home",PersonalActivity::class.java to "personal")){
            val activity=instrumentation.startActivitySync(Intent(context,type).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            try{
                instrumentation.waitForIdleSync()
                val screenshot=instrumentation.getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES).takeScreenshot()
                assertNotNull(screenshot)
                File(context.cacheDir,"qa-$name.png").outputStream().use{screenshot.compress(android.graphics.Bitmap.CompressFormat.PNG,100,it)}
                screenshot.recycle()
            }finally{instrumentation.runOnMainSync{activity.finish()}}
        }
    }
    @Test fun memoriesAndTasksSurviveStoreRecreationAndReminderStopsAfterCompletion(){
        val store=SecureStore(context);val oldMemory=store.get("memories","[]");val oldTasks=store.get("tasks","[]")
        var id=""
        try{
            store.put("memories","[]");store.put("tasks","[]")
            assertTrue(FeatureTools.execute(context,"memory",JSONObject().put("action","remember").put("key","teste").put("value","informacao privada")).getBoolean("ok"))
            assertTrue(SecureStore(context).get("memories").contains("informacao privada"))
            assertFalse(context.getSharedPreferences("jarvis_private",0).getString("memories","")!!.contains("informacao privada"))
            assertEquals(1,PersonalData.memory(context,"recall",JSONObject().put("query","privada")).getJSONArray("memories").length())
            val created=PersonalData.tasks(context,"add",JSONObject().put("title","Tarefa de teste").put("due",OffsetDateTime.now().plusHours(1).toString()))
            id=created.getJSONObject("task").getString("id")
            assertEquals(id,JSONArray(SecureStore(context).get("tasks")).getJSONObject(0).getString("id"))
            val automation=InstrumentationRegistry.getInstrumentation().getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES)
            if(android.os.Build.VERSION.SDK_INT>=33)ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand("pm grant ${context.packageName} android.permission.POST_NOTIFICATIONS")).use{it.readBytes()}
            val entries=PersonalData.read(context,"tasks");entries.getJSONObject(0).put("due_ms",System.currentTimeMillis()-1000);PersonalData.write(context,"tasks",entries)
            TaskReminderReceiver().onReceive(context,Intent("remind").putExtra("id",id))
            assertTrue(PersonalData.read(context,"tasks").getJSONObject(0).getBoolean("notified"))
            PersonalData.tasks(context,"complete",JSONObject().put("id",id))
            assertEquals(0,PersonalData.tasks(context,"list",JSONObject()).getJSONArray("tasks").length())
            assertFalse(context.getSystemService(NotificationManager::class.java).activeNotifications.any{it.tag==id})
            assertFalse(FeatureTools.execute(context,"tasks",JSONObject().put("action","add").put("title","Passado").put("due","2020-01-01T12:00:00-03:00")).getBoolean("ok"))
            PersonalData.memory(context,"forget",JSONObject().put("key","teste"));assertEquals(0,PersonalData.read(context,"memories").length())
        }finally{if(id.isNotBlank())TaskReminders.cancel(context,id);store.put("memories",oldMemory);store.put("tasks",oldTasks)}
    }
    @Test fun authorizedFilesReadTextAndPdfWhileGeneratedNotesRemainEncrypted(){
        val store=SecureStore(context);val old=store.get("documents","[]");var created=""
        val directory=File(context.cacheDir,"camera").apply{mkdirs()}
        val source=File(directory,"fixture-home.txt").apply{writeText("Documento autorizado do teste")}
        val pdfFile=File(directory,"fixture-home.pdf")
        try{
            store.put("documents","[]")
            val attached=PersonalFiles.attach(context,FileProvider.getUriForFile(context,"${context.packageName}.files",source))
            val read=PersonalFiles.execute(context,"read",JSONObject().put("id",attached.getString("id")))
            assertEquals("Documento autorizado do teste",read.getString("text"))
            assertFalse(attached.has("uri"))
            val made=PersonalFiles.execute(context,"create",JSONObject().put("name","Minha nota").put("text","Nota criptografada"))
            created=made.getJSONObject("file").getString("id")
            PersonalFiles.execute(context,"update",JSONObject().put("id",created).put("text","Nota atualizada"))
            assertEquals("Nota atualizada",PersonalFiles.execute(context,"read",JSONObject().put("id",created)).getString("text"))
            assertFalse(FeatureTools.execute(context,"files",JSONObject().put("action","read").put("id","../../private")).getBoolean("ok"))
            assertFalse(FeatureTools.execute(context,"files",JSONObject().put("action","create").put("name","../../escape").put("text","x")).getBoolean("ok"))
            val pdfDocument=android.graphics.pdf.PdfDocument()
            try{val pdf=pdfDocument
                val page=pdf.startPage(android.graphics.pdf.PdfDocument.PageInfo.Builder(300,400,1).create())
                page.canvas.drawColor(android.graphics.Color.WHITE);page.canvas.drawText("PDF autorizado",20f,50f,android.graphics.Paint().apply{color=android.graphics.Color.BLACK;textSize=18f})
                pdf.finishPage(page);pdfFile.outputStream().use{pdf.writeTo(it)}
            }finally{pdfDocument.close()}
            val pdf=PersonalFiles.attach(context,FileProvider.getUriForFile(context,"${context.packageName}.files",pdfFile))
            val image=PersonalFiles.execute(context,"read",JSONObject().put("id",pdf.getString("id")).put("page",1))
            assertEquals(1,image.getInt("pages"));assertTrue(image.getString("image").isNotBlank())
            assertFalse(FeatureTools.execute(context,"files",JSONObject().put("action","read").put("id",pdf.getString("id")).put("page",2)).getBoolean("ok"))
            PersonalFiles.execute(context,"unlink",JSONObject().put("id",attached.getString("id")))
            assertTrue(source.exists())
        }finally{store.put("documents",old);if(created.isNotEmpty())store.put("document_$created","");source.delete();pdfFile.delete()}
    }
    @Test fun importedHomeConfigKeepsSecretsOutOfAgentResultsAndValidatesDvrChannels(){
        val store=SecureStore(context);val old=store.get("home_cameras","[]");val oldKey=store.get("tuya_key");val oldSecret=store.get("tuya_secret");val oldRegion=store.get("tuya_region","us")
        try{
            store.put("home_cameras","[]")
            val data=JSONObject("""{"version":1,"cameras":[{"id":"dvr-test","name":"Intelbras teste","host":"192.168.1.9","vendor":"intelbras","username":"admin","password":"camera-private","channel_count":16}],"tuya":{"api_key":"fake-key","api_secret":"tuya-private","region":"us"}}""")
            HomeConfig.importPc(context,data)
            assertEquals("camera-private",CameraTools.list(context).getJSONObject(0).getString("password"))
            val listed=CameraTools.execute(context,"list",JSONObject()).toString()
            assertFalse(listed.contains("private"));assertFalse(listed.contains("admin"))
            val camera=CameraTools.selected(context,"intelbras")
            assertTrue(CameraTools.url(camera,12).contains("channel=12"))
            assertFalse(FeatureTools.execute(context,"camera",JSONObject().put("action","open").put("name","dvr-test").put("channel",17)).getBoolean("ok"))
            assertEquals(16,CameraTools.list(context).getJSONObject(0).getInt("channel_count"))
        }finally{store.put("home_cameras",old);store.put("tuya_key",oldKey);store.put("tuya_secret",oldSecret);store.put("tuya_region",oldRegion)}
    }
    @Test fun tuyaSignedCommandIsSentOnceAndVerifiedWithoutReturningSecrets(){
        val store=SecureStore(context);val oldKey=store.get("tuya_key");val oldSecret=store.get("tuya_secret")
        val server=MockWebServer()
        fun body(value:String)=MockResponse().setBody(value)
        server.enqueue(body("""{"success":true,"result":{"access_token":"test-token"}}"""))
        server.enqueue(body("""{"success":true,"result":{"devices":[{"id":"light-1","name":"Sala","online":true,"local_key":"must-not-leak"}],"has_more":false}}"""))
        server.enqueue(body("""{"success":true,"result":[{"code":"switch_led","value":false}]}"""))
        server.enqueue(body("""{"success":true,"result":true}"""))
        server.enqueue(body("""{"success":true,"result":[{"code":"switch_led","value":true}]}"""))
        server.start();store.put("tuya_key","fake-key");store.put("tuya_secret","fake-secret")
        try{
            val result=TuyaClient(context,server.url("/").toString().trimEnd('/')).execute("on",JSONObject().put("name","Sala"))
            assertTrue(result.getBoolean("verified"));assertFalse(result.toString().contains("must-not-leak"))
            val requests=(0..4).map{server.takeRequest(5,TimeUnit.SECONDS)!!}
            assertEquals(1,requests.count{it.method=="POST"})
            val command=requests[3];val raw=command.body.readUtf8()
            assertEquals("test-token",command.getHeader("access_token"))
            assertEquals(TuyaClient.sign("fake-key","fake-secret","test-token",command.getHeader("t")!!,"POST",command.path!!,raw),command.getHeader("sign"))
            assertEquals(true,JSONObject(raw).getJSONArray("commands").getJSONObject(0).getBoolean("value"))
            assertEquals(5,server.requestCount)
            assertThrows(IllegalArgumentException::class.java){TuyaClient(context,server.url("/").toString()).execute("brightness",JSONObject().put("percent",101))}
            assertEquals(5,server.requestCount)
        }finally{server.shutdown();store.put("tuya_key",oldKey);store.put("tuya_secret",oldSecret)}
    }
    @Test fun tuyaOfflineDeviceAndFailedCommandAreNeverRepeated(){
        val store=SecureStore(context);val oldKey=store.get("tuya_key");val oldSecret=store.get("tuya_secret")
        store.put("tuya_key","fake-key");store.put("tuya_secret","fake-secret")
        try{
            for(online in listOf(false,true)){
                val server=MockWebServer()
                server.enqueue(MockResponse().setBody("""{"success":true,"result":{"access_token":"test-token"}}"""))
                server.enqueue(MockResponse().setBody("""{"success":true,"result":{"devices":[{"id":"light-1","name":"Sala","online":$online}],"has_more":false}}"""))
                server.enqueue(MockResponse().setBody("""{"success":true,"result":[{"code":"switch_led","value":false}]}"""))
                if(online)server.enqueue(MockResponse().setResponseCode(503))
                server.start()
                try{
                    assertThrows(IllegalStateException::class.java){TuyaClient(context,server.url("/").toString().trimEnd('/')).execute("on",JSONObject().put("name","Sala"))}
                    assertEquals(if(online)4 else 3,server.requestCount)
                }finally{server.shutdown()}
            }
        }finally{store.put("tuya_key",oldKey);store.put("tuya_secret",oldSecret)}
    }
}
