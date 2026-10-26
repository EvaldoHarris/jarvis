package com.evaldoharris.jarvis

import org.junit.Assert.*
import org.junit.Test

class GeminiModelPolicyTest {
    @Test fun normalizesApiModelNamesAndRejectsPaths() {
        assertEquals("gemini-2.5-flash", GeminiModelPolicy.normalize(" models/gemini-2.5-flash "))
        assertThrows(IllegalArgumentException::class.java) { GeminiModelPolicy.normalize("../other?key=secret") }
    }
    @Test fun missingModelIsNotReportedAsQuota() {
        val error = GeminiModelPolicy.error(404, "gemini-old", "NOT_FOUND")
        assertTrue(error.contains("não encontrado"))
        assertFalse(error.contains("cota"))
        assertTrue(GeminiModelPolicy.error(429, "gemini-current", "RESOURCE_EXHAUSTED").contains("cota"))
        assertTrue(GeminiModelPolicy.error(503, "gemini-current", "high demand").contains("sobrecarregado"))
    }
    @Test fun fallbackUsesListedFlashOnlyAndDoesNotUpgradeLiteToFullModel() {
        val available = listOf("gemini-3.8-pro", "gemini-3.8-flash", "gemini-3.8-flash-image", "gemini-3.8-flash-lite")
        assertEquals("gemini-3.8-flash", GeminiModelPolicy.fallback("gemini-2.5-flash", available, emptySet()))
        assertEquals("gemini-3.8-flash-lite", GeminiModelPolicy.fallback("gemini-2.5-flash-lite", available, emptySet()))
        assertNull(GeminiModelPolicy.fallback("gemini-2.5-pro", available, emptySet()))
        assertNull(GeminiModelPolicy.fallback("gemini-2.5-flash", listOf("gemini-3.8-pro"), emptySet()))
    }
}
