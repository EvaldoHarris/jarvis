package com.evaldoharris.jarvis

import org.junit.Assert.*
import org.junit.Test

class HomePolicyTest {
    @Test fun dvrUsesRequestedChannelAndEscapesCredentials() {
        val url=CameraAddress.build("192.168.1.9",554,"intelbras","admin","p@ss word",12,1,16)
        assertTrue(url.contains("admin:p%40ss%20word@"));assertTrue(url.endsWith("channel=12&subtype=1"))
        assertTrue(CameraAddress.build("10.0.1.5",554,"icsee","a","b",2,1).endsWith("channel=2&stream=1.sdp"))
        assertThrows(IllegalArgumentException::class.java){CameraAddress.build("8.8.8.8",554,"intelbras","a","b",1,1)}
        assertThrows(IllegalArgumentException::class.java){CameraAddress.build("192.168.1.9",554,"intelbras","a","b",17,1,16)}
        assertThrows(IllegalArgumentException::class.java){CameraAddress.build("127.0.0.1",554,"intelbras","a","b",1,1)}
    }
    @Test fun tuyaSignatureIncludesAccessTokenBodyAndPath() {
        val body="""{"commands":[{"code":"switch_led","value":true}]}"""
        assertEquals("022E5DEC8F5CF2EE3502BC23DC3676EE74B55503E0515644C4033FBA38D2CD57",TuyaClient.sign("test-key","test-secret","test-token","1700000000000","POST","/v1.0/devices/light-1/commands",body))
        assertNotEquals(TuyaClient.sign("k","s","","1","GET","/a",""),TuyaClient.sign("k","s","token","1","GET","/a",""))
    }
    @Test fun readsAtMostLimitPlusOneByteOnOlderAndroid() {
        val input=ByteArray(100){it.toByte()}.inputStream()
        assertEquals(11,input.readBounded(10).size)
        assertEquals(2,byteArrayOf(1,2).inputStream().readBounded(10).size)
    }
}
