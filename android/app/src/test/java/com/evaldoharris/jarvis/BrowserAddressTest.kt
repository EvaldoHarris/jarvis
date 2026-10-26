package com.evaldoharris.jarvis

import org.junit.Assert.*
import org.junit.Test

class BrowserAddressTest {
    @Test fun acceptsWebAddressesAndEncodesSearchAsData() {
        assertEquals("https://example.com/hotel", BrowserAddress.normalize("example.com/hotel"))
        assertEquals("http://127.0.0.1:8080/test", BrowserAddress.normalize("http://127.0.0.1:8080/test"))
        assertTrue(BrowserAddress.search("Golden Garden & praia").contains("Golden+Garden+%26+praia"))
    }
    @Test fun rejectsExecutableAndPrivateFileSchemesAndEmbeddedPasswords() {
        for (url in listOf("javascript:alert(1)", "file:///data/data/config", "content://settings", "intent://app", "https://user:password@example.com", "https://")) {
            assertThrows(Exception::class.java) { BrowserAddress.normalize(url) }
        }
    }
}
