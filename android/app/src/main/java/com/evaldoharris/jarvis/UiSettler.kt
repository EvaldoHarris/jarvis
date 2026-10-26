package com.evaldoharris.jarvis

internal object UiSettler {
    fun await(before:Long,cancelled:()->Boolean) {
        val started=android.os.SystemClock.elapsedRealtime()
        while(!cancelled()){
            val now=android.os.SystemClock.elapsedRealtime()
            val changed=JarvisAccessibilityService.windowVersion.get()!=before
            if(now-started>=1000 || (changed&&now-started>=100&&now-JarvisAccessibilityService.lastChange>=100) || (!changed&&now-started>=250))return
            Thread.sleep(25)
        }
    }
}
