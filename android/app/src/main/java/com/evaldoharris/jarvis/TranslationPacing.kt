package com.evaldoharris.jarvis

/** Pitch-preserving acceleration catches up without discarding phrases. */
internal object TranslationPacing {
    fun speed(waitMs:Long,queued:Int):Float {
        if(queued<=0)return 1.08f
        return when {
            waitMs>=12000||queued>=4->1.45f
            waitMs>=7000||queued>=2->1.30f
            else->1.18f
        }
    }
}
