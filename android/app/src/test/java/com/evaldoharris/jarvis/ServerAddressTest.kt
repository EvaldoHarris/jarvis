package com.evaldoharris.jarvis

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class ServerAddressTest {
    @Test fun acceptsLanAndPrivateVpnAddresses() {
        assertEquals("http://192.168.15.13:8000", ServerAddress.normalize(" http://192.168.15.13:8000/ "))
        assertEquals("http://100.101.2.3:8000", ServerAddress.normalize("http://100.101.2.3:8000"))
        assertEquals("https://jarvis.example.org", ServerAddress.normalize("https://jarvis.example.org"))
    }
    @Test fun rejectsCredentialsPublicHttpAndPairingLinks() {
        for (url in listOf("http://8.8.8.8:8000", "http://public.example.com", "file:///etc/passwd", "http://user:pass@192.168.1.2", "http://192.168.1.2/auto-login?key=SECRET"))
            assertThrows(IllegalArgumentException::class.java) { ServerAddress.normalize(url) }
    }
}
