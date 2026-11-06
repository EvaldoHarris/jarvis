package com.evaldoharris.jarvis

import android.accessibilityservice.AccessibilityService
import android.app.UiAutomation
import android.content.Intent
import android.graphics.Bitmap
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean

@RunWith(AndroidJUnit4::class)
class FloatingReactorIntegrationTest {
    @Test fun singleTapArmsListeningAndDoubleTapOnlyOpensApp() {
        val instrument=InstrumentationRegistry.getInstrumentation();val context=instrument.targetContext
        val automation=instrument.getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES)
        val store=SecureStore(context);val oldMode=store.get("voice_mode","wake");val oldLive=store.get("live_agent","true")
        var activity:android.app.Activity?=null
        fun await(condition:()->Boolean) {
            val ok=AtomicBoolean(false);val deadline=System.currentTimeMillis()+7000
            while(!ok.get()&&System.currentTimeMillis()<deadline){instrument.runOnMainSync{ok.set(condition())};if(!ok.get())Thread.sleep(50)}
            assertTrue("Reactor gesture condition timed out",ok.get())
        }
        fun tap(rect:android.graphics.Rect) {
            val x=rect.centerX().toFloat();val y=rect.centerY().toFloat();val start=android.os.SystemClock.uptimeMillis()
            val down=android.view.MotionEvent.obtain(start,start,android.view.MotionEvent.ACTION_DOWN,x,y,0).apply{source=android.view.InputDevice.SOURCE_TOUCHSCREEN}
            automation.injectInputEvent(down,false);down.recycle();Thread.sleep(25)
            val up=android.view.MotionEvent.obtain(start,android.os.SystemClock.uptimeMillis(),android.view.MotionEvent.ACTION_UP,x,y,0).apply{source=android.view.InputDevice.SOURCE_TOUCHSCREEN}
            automation.injectInputEvent(up,false);up.recycle()
        }
        try {
            store.put("voice_mode","off");store.put("live_agent","false")
            await{JarvisAccessibilityService.current!=null}
            activity=instrument.startActivitySync(Intent(context,MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            context.stopService(Intent(context,WakeListeningService::class.java))
            JarvisAccessibilityService.current!!.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME)
            await{!AppState.mainVisible&&JarvisAccessibilityService.current?.reactorVisible()==true}
            var rect:android.graphics.Rect?=null
            instrument.runOnMainSync{rect=JarvisAccessibilityService.current!!.reactorBounds()}
            tap(rect!!);Thread.sleep(70);tap(rect!!)
            await{AppState.mainVisible}
            assertTrue("Double tap must not start a listening window",WakeListeningService.current?.tapArmed()!=true)
            JarvisAccessibilityService.current!!.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME)
            await{!AppState.mainVisible&&JarvisAccessibilityService.current?.reactorVisible()==true}
            instrument.runOnMainSync{rect=JarvisAccessibilityService.current!!.reactorBounds()}
            tap(rect!!)
            await{WakeListeningService.current?.tapArmed()==true}
            assertFalse("Single tap should listen without opening the app",AppState.mainVisible)
        } finally {
            context.stopService(Intent(context,WakeListeningService::class.java))
            instrument.runOnMainSync{activity?.finish()}
            store.put("voice_mode",oldMode);store.put("live_agent",oldLive)
        }
    }
    @Test fun reactorReturnsOnHomeAndHidesWhenMainAppIsVisible() {
        val instrument=InstrumentationRegistry.getInstrumentation()
        val context=instrument.targetContext
        val automation=instrument.getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES)
        val store=SecureStore(context)
        val oldMode=store.get("voice_mode","wake");val oldLive=store.get("live_agent","true")
        var activity:android.app.Activity?=null
        fun await(condition:()->Boolean) {
            val result=AtomicBoolean(false);val deadline=System.currentTimeMillis()+7000
            while(!result.get()&&System.currentTimeMillis()<deadline) {
                instrument.runOnMainSync { result.set(condition()) }
                if(!result.get())Thread.sleep(100)
            }
            assertTrue("Floating reactor lifecycle condition timed out",result.get())
        }
        try {
            store.put("voice_mode","off");store.put("live_agent","false")
            await { JarvisAccessibilityService.current!=null }
            activity=instrument.startActivitySync(Intent(context,MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            await { AppState.mainVisible && JarvisAccessibilityService.current?.reactorVisible()==false }
            assertTrue(JarvisAccessibilityService.current!!.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME))
            await { !AppState.mainVisible && JarvisAccessibilityService.current?.reactorVisible()==true }
            var bounds:android.graphics.Rect?=null
            instrument.runOnMainSync { bounds=JarvisAccessibilityService.current!!.reactorBounds() }
            val image=automation.takeScreenshot()
            val rect=bounds!!
            val crop=Bitmap.createBitmap(image,rect.left,rect.top,rect.width(),rect.height())
            File(context.cacheDir,"qa-floating-reactor.png").outputStream().use { crop.compress(Bitmap.CompressFormat.PNG,100,it) }
            crop.recycle();image.recycle()
            context.startActivity(Intent(context,MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP))
            await { AppState.mainVisible && JarvisAccessibilityService.current?.reactorVisible()==false }
            assertTrue(JarvisAccessibilityService.current!!.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME))
            await { !AppState.mainVisible && JarvisAccessibilityService.current?.reactorVisible()==true }
        } finally {
            instrument.runOnMainSync { activity?.finish() }
            store.put("voice_mode",oldMode);store.put("live_agent",oldLive)
        }
    }
}
