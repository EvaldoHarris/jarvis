package com.evaldoharris.jarvis

import okhttp3.*
import okio.ByteString
import org.json.JSONObject

/** Prepares the handshake while the text agent works; never sends text or plays audio. */
internal class PreparedVoiceSocket(client:OkHttpClient,url:String,private val setup:String,val identity:String) {
    private val lock=Any()
    private var listener:WebSocketListener?=null
    private var ready=false
    private var closed=false
    val socket:WebSocket=client.newWebSocket(Request.Builder().url(url).build(),object:WebSocketListener(){
        override fun onOpen(ws:WebSocket,response:Response){synchronized(lock){if(closed)ws.cancel() else ws.send(setup)}}
        override fun onMessage(ws:WebSocket,text:String){
            val target=synchronized(lock){
                if(closed)return
                val target=listener
                if(target==null){
                val message=runCatching{JSONObject(text)}.getOrNull()
                if(message?.has("setupComplete")==true)ready=true
                else if(message?.has("error")==true||message?.has("serverContent")==true){closed=true;ws.cancel()}
                }
                target
            }
            target?.onMessage(ws,text)
        }
        override fun onMessage(ws:WebSocket,bytes:ByteString)=onMessage(ws,bytes.utf8())
        override fun onFailure(ws:WebSocket,t:Throwable,response:Response?){val target=synchronized(lock){closed=true;listener};target?.onFailure(ws,t,response)}
        override fun onClosing(ws:WebSocket,code:Int,reason:String){val target=synchronized(lock){closed=true;listener};if(target!=null)target.onClosing(ws,code,reason)else ws.close(code,null)}
        override fun onClosed(ws:WebSocket,code:Int,reason:String){val target=synchronized(lock){closed=true;listener};target?.onClosed(ws,code,reason)}
    })
    fun attach(target:WebSocketListener):Boolean {
        val wasReady=synchronized(lock){if(closed)return false;listener=target;ready}
        if(wasReady)target.onMessage(socket,"{\"setupComplete\":{}}")
        return true
    }
    fun close(){synchronized(lock){closed=true;socket.cancel()}}
}
