package com.evaldoharris.jarvis

import java.io.ByteArrayOutputStream
import java.io.InputStream

internal fun InputStream.readBounded(limit:Int):ByteArray {
    val output=ByteArrayOutputStream();val buffer=ByteArray(8192)
    while(output.size()<=limit){
        val count=read(buffer,0,minOf(buffer.size,limit+1-output.size()))
        if(count<0)break
        if(count==0)continue
        output.write(buffer,0,count)
        if(output.size()>limit)break
    }
    return output.toByteArray()
}
