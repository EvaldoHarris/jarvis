package com.evaldoharris.jarvis

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.*
import org.junit.Test
import java.nio.file.Files
import java.security.MessageDigest

class ModelTransferTest {
    private fun checkTransfer(body: String, size: Long, digest: String, cancelled: Boolean = false, success: Boolean) {
        val folder = Files.createTempDirectory("jarvis-model-test").toFile()
        val target = java.io.File(folder, "model.litertlm").apply { writeText("old model") }
        val server = MockWebServer()
        server.enqueue(MockResponse().setBody(body)); server.start()
        try {
            val call = OkHttpClient().newCall(Request.Builder().url(server.url("/model")).build())
            val result = runCatching { VerifiedModelTransfer.transfer(call, target, size, digest, { cancelled }) }
            assertEquals(success, result.isSuccess)
            assertEquals(if (success) body else "old model", target.readText())
            assertFalse(java.io.File(folder, "model.litertlm.download").exists())
        } finally { server.shutdown(); folder.deleteRecursively() }
    }
    private val body = "verified model fixture"
    private val digest get() = MessageDigest.getInstance("SHA-256").digest(body.toByteArray()).joinToString("") { "%02x".format(it) }
    @Test fun verifiedCompleteDownloadReplacesOldModel() = checkTransfer(body, body.length.toLong(), digest, success = true)
    @Test fun wrongDigestPreservesOldModel() = checkTransfer(body, body.length.toLong(), "0".repeat(64), success = false)
    @Test fun truncatedDownloadPreservesOldModel() = checkTransfer(body, body.length + 4L, digest, success = false)
    @Test fun oversizedDownloadPreservesOldModel() = checkTransfer(body, body.length - 1L, digest, success = false)
    @Test fun cancellationPreservesOldModel() = checkTransfer(body, body.length.toLong(), digest, cancelled = true, success = false)
}
