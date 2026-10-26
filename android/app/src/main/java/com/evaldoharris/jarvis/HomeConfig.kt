package com.evaldoharris.jarvis

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

object HomeConfig {
    fun validate(camera: JSONObject): JSONObject {
        val copy = JSONObject()
        for (key in listOf("id","name","host","vendor","username","password")) copy.put(key,camera.optString(key).take(if(key=="password")500 else 120))
        require(copy.getString("id").matches(Regex("[a-zA-Z0-9_-]{1,100}")) && copy.getString("name").isNotBlank()) { "Nome ou identificador de câmera inválido." }
        for ((key,default) in listOf("port" to 554,"channel" to 1,"stream" to 1,"channel_count" to 64)) copy.put(key,camera.optInt(key,default))
        CameraAddress.build(copy.getString("host"),copy.getInt("port"),copy.getString("vendor"),copy.optString("username").ifBlank{"_"},copy.optString("password").ifBlank{"_"},copy.getInt("channel"),copy.getInt("stream"),copy.getInt("channel_count"))
        return copy
    }
    @Synchronized fun save(context:Context,camera:JSONObject) {
        val validated=validate(camera)
        val cameras=CameraTools.list(context)
        val index=(0 until cameras.length()).firstOrNull{cameras.getJSONObject(it).getString("id")==validated.getString("id")}
        require(index!=null||cameras.length()<20){"Limite de 20 dispositivos de câmera."}
        cameras.put(index?:cameras.length(),validated); PersonalData.write(context,"home_cameras",cameras)
    }
    @Synchronized fun importPc(context:Context,data:JSONObject) {
        require(data.optInt("version")==1)
        val incoming=data.getJSONArray("cameras"); require(incoming.length()<=20)
        val checked=(0 until incoming.length()).map{validate(incoming.getJSONObject(it))}
        val cameras=CameraTools.list(context)
        val merged=LinkedHashMap<String,JSONObject>()
        for(i in 0 until cameras.length()) cameras.getJSONObject(i).let{merged[it.getString("id")]=it}
        checked.forEach{merged[it.getString("id")]=it}
        require(merged.size<=20)
        val tuya=data.optJSONObject("tuya")?:JSONObject()
        val region=tuya.optString("region").ifBlank{"us"}
        require(region in listOf("us","us-e","eu","eu-w","cn","in"))
        val store=SecureStore(context)
        store.put("tuya_key",tuya.optString("api_key").take(200)); store.put("tuya_secret",tuya.optString("api_secret").take(500)); store.put("tuya_region",region)
        PersonalData.write(context,"home_cameras",JSONArray(merged.values.toList()))
    }
}
