package com.evaldoharris.jarvis

import org.json.JSONArray
import org.json.JSONObject

internal object AgentHistory {
    /** Keep original user attachments and only the latest tool screenshot on the wire. */
    fun contents(history:List<JSONObject>):JSONArray {
        val copy=JSONArray(JSONArray(history).toString())
        var keepLatest=true
        var latestToolTurn=true
        for(i in copy.length()-1 downTo 0){
            val parts=copy.getJSONObject(i).optJSONArray("parts")?:continue
            if((0 until parts.length()).none{parts.getJSONObject(it).has("functionResponse")})continue
            for(j in parts.length()-1 downTo 0){
                val part=parts.getJSONObject(j)
                if(part.has("inlineData")){
                    if(keepLatest)keepLatest=false else parts.remove(j)
                }
                // Leituras de tela antigas já não valem: manda só o resultado, não a árvore inteira.
                if(!latestToolTurn) part.optJSONObject("functionResponse")?.optJSONObject("response")?.let{ response->
                    response.remove("observation"); response.remove("nodes"); response.remove("tree")
                    for(key in response.keys().asSequence().toList()){
                        val value=response.opt(key)
                        if(value is String&&value.length>400)response.put(key,value.take(400)+"…")
                        else if(value is JSONArray&&value.length()>20)response.put(key,"[${value.length()} itens omitidos]")
                    }
                }
            }
            latestToolTurn=false
        }
        return copy
    }
}
