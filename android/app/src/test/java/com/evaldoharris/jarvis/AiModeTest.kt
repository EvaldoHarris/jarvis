package com.evaldoharris.jarvis
import org.junit.Assert.*
import org.junit.Test
class AiModeTest {
 @Test fun explicitModesNeverSwitchProvider() {
  assertFalse(AiMode.fallback("gemini", true, true, false))
  assertFalse(AiMode.fallback("local", true, true, false))
 }
 @Test fun automaticNeedsTransientFailureAndInstalledModel() {
  assertTrue(AiMode.fallback("auto", true, true, false))
  assertFalse(AiMode.fallback("auto", false, true, false))
  assertFalse(AiMode.fallback("auto", true, false, false))
  assertFalse(AiMode.fallback("auto", true, true, true))
 }
 @Test fun oldInstallDefaultsToAutomatic() { assertEquals("auto", AiMode.normalize("")) }
}
