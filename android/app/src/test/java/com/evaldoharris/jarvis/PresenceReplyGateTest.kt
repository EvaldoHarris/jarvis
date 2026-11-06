package com.evaldoharris.jarvis

import org.junit.Assert.*
import org.junit.Test

class PresenceReplyGateTest {
    private val request = "presence_" + "a".repeat(24)
    @Test fun onlyFreshConfirmedStreamIsAccepted() {
        val gate = PresenceReplyGate()
        assertFalse(gate.accepts(request, 1000))
        assertFalse(gate.start(request, false, 5000, 1000))
        assertFalse(gate.start(request, true, 0, 1000))
        assertFalse(gate.start("unexpected", true, 5000, 1000))
        assertTrue(gate.start(request, true, 5000, 1000))
        assertTrue(gate.accepts(request, 1001))
        assertFalse(gate.accepts("presence_" + "b".repeat(24), 1001))
        gate.clear()
        assertFalse(gate.accepts(request, 1002))
    }
    @Test fun inactiveStreamExpiresAndLiveAudioRenewsIt() {
        val gate = PresenceReplyGate()
        assertTrue(gate.start(request, true, 5000, 1000))
        gate.touch(50000)
        assertTrue(gate.accepts(request, 100000))
        assertFalse(gate.accepts(request, 110001))
    }
    @Test fun pcAndPhoneWallClocksNeedNotAgree() {
        val gate = PresenceReplyGate()
        assertTrue(gate.start(request, true, 5000, 123456789))
        assertTrue(gate.accepts(request, 123456790))
        assertFalse(gate.start(request, true, 600000, 123456789))
    }
}
