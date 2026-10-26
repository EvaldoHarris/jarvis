package com.evaldoharris.jarvis

import android.content.Intent
import android.graphics.Rect
import android.widget.ScrollView
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class WakeFeedbackIntegrationTest {
    @Test fun pronunciationSetupPausesWakeListenerAndReleasesItWhenLeaving(){
        val instrumentation=InstrumentationRegistry.getInstrumentation()
        val context=instrumentation.targetContext
        val before=AppState.manualListening
        val activity=instrumentation.startActivitySync(Intent(context,WakeCalibrationActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        try{
            instrumentation.waitForIdleSync();assertTrue(AppState.manualListening)
            val image=instrumentation.getUiAutomation(android.app.UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES).takeScreenshot()
            java.io.File(context.cacheDir,"qa-wake-calibration.png").outputStream().use{image.compress(android.graphics.Bitmap.CompressFormat.PNG,100,it)};image.recycle()
        }finally{instrumentation.runOnMainSync{activity.finish()};instrumentation.waitForIdleSync()}
        val until=System.currentTimeMillis()+3000
        while(AppState.manualListening&&System.currentTimeMillis()<until)Thread.sleep(25)
        assertFalse(AppState.manualListening);AppState.manualListening=before
    }
    @Test fun readyBannerStaysVisibleWhileReadingConversationAndClearsAfterTimeout(){
        val instrumentation=InstrumentationRegistry.getInstrumentation()
        val context=instrumentation.targetContext
        val store=SecureStore(context);val previousMode=store.get("voice_mode","wake")
        store.put("voice_mode","off")
        val activity=instrumentation.startActivitySync(Intent(context,MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as MainActivity
        val previousPhase=AppState.phase;val previousWake=AppState.wakeRunning;val previousUntil=AppState.wakeReadyUntil
        val previousBusy=AppState.assistantBusy;val previousAudio=AppState.audioBusy;val previousManual=AppState.manualListening;val previousReply=AppState.expectedPhoneReply
        try{
            instrumentation.runOnMainSync{
                store.put("voice_mode","wake")
                AppState.wakeRunning=true;AppState.wakeReadyUntil=System.currentTimeMillis()+10000
                AppState.assistantBusy=false;AppState.audioBusy=false;AppState.manualListening=false;AppState.expectedPhoneReply=""
                AppState.phase="PODE FALAR"
                repeat(15){AppState.message("TESTE","Mensagem longa para verificar a leitura da conversa sem esconder a indicação de escuta. ".repeat(8))}
                AppState.update()
            }
            instrumentation.waitForIdleSync()
            var before=Rect();var after=Rect()
            instrumentation.runOnMainSync{
                val banner=activity.findViewById<TextView>(R.id.wake_status)
                assertTrue(banner.text.contains("PODE FALAR"))
                assertTrue(banner.getGlobalVisibleRect(before))
                assertEquals(android.graphics.Color.rgb(0,255,165),banner.currentTextColor)
                activity.findViewById<ScrollView>(R.id.conversation_scroll).fullScroll(android.view.View.FOCUS_DOWN)
            }
            instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync{assertTrue(activity.findViewById<TextView>(R.id.wake_status).getGlobalVisibleRect(after))}
            assertEquals(before,after)
            val automation=instrumentation.getUiAutomation(android.app.UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES)
            val image=automation.takeScreenshot()
            java.io.File(context.cacheDir,"qa-wake-ready.png").outputStream().use{image.compress(android.graphics.Bitmap.CompressFormat.PNG,100,it)};image.recycle()
            instrumentation.runOnMainSync{AppState.wakeReadyUntil=0;AppState.phase="AGUARDANDO JARVIS";AppState.update()}
            instrumentation.waitForIdleSync()
            instrumentation.runOnMainSync{assertTrue(activity.findViewById<TextView>(R.id.wake_status).text.contains("DIGA JARVIS"))}
            assertFalse(AppState.readyForCommand())
        }finally{
            store.put("voice_mode",previousMode);AppState.phase=previousPhase;AppState.wakeRunning=previousWake;AppState.wakeReadyUntil=previousUntil
            AppState.assistantBusy=previousBusy;AppState.audioBusy=previousAudio;AppState.manualListening=previousManual;AppState.expectedPhoneReply=previousReply
            instrumentation.runOnMainSync{activity.finish()}
        }
    }
}
