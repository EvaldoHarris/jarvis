package com.evaldoharris.jarvis

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.time.OffsetDateTime
import java.util.UUID

/** Bounded personal stores, encrypted by Android Keystore, separate from PC memory. */
object PersonalData {
    @Synchronized fun read(context: Context, key: String): JSONArray = JSONArray(SecureStore(context).get(key, "[]"))
    @Synchronized fun write(context: Context, key: String, values: JSONArray) { SecureStore(context).put(key, values.toString()) }
    @Synchronized fun importMemories(context:Context,data:JSONObject):Int {
        val incoming=data.getJSONArray("memories");require(incoming.length()<=200)
        val existing=read(context,"memories");val merged=LinkedHashMap<String,JSONObject>()
        for(i in 0 until existing.length())existing.getJSONObject(i).let{merged[it.getString("key").lowercase()]=it}
        for(i in 0 until incoming.length())incoming.getJSONObject(i).let{item->
            val key=("PC | "+item.getString("key")).take(120);val value=item.getString("value").take(2000)
            if(value.isNotBlank())merged[key.lowercase()]=JSONObject().put("key",key).put("value",value)
        }
        require(merged.size<=200){"A importação excede 200 memórias. Remova algumas e tente novamente."}
        write(context,"memories",JSONArray(merged.values.toList()));return incoming.length()
    }
    @Synchronized fun memory(context: Context, action: String, args: JSONObject): JSONObject {
        val entries = read(context, "memories")
        val key = args.optString("key").trim()
        when (action) {
            "remember" -> {
                val value = args.optString("value").trim()
                require(key.length in 1..120 && value.length in 1..2000) { "Informe um nome (até 120 caracteres) e informação (até 2000)." }
                val index = (0 until entries.length()).firstOrNull { entries.getJSONObject(it).getString("key").equals(key, true) }
                require(index != null || entries.length() < 200) { "A memória chegou a 200 informações. Remova uma antes de adicionar." }
                entries.put(index ?: entries.length(), (if (index == null) JSONObject() else JSONObject(entries.getJSONObject(index).toString())).put("key", key).put("value", value))
                write(context, "memories", entries)
                return PhoneTools.result(true).put("saved", key)
            }
            "forget" -> {
                val index = (0 until entries.length()).firstOrNull { entries.getJSONObject(it).getString("key").equals(key, true) }
                    ?: return PhoneTools.result(false, "Informação não encontrada.")
                entries.remove(index); write(context, "memories", entries)
                return PhoneTools.result(true).put("forgotten", key)
            }
            "recall", "list" -> {
                val query = args.optString("query", key).trim()
                val matches = JSONArray()
                for (i in 0 until entries.length()) {
                    val item = entries.getJSONObject(i)
                    if (query.isBlank() || item.getString("key").contains(query, true) || item.getString("value").contains(query, true)) matches.put(item)
                }
                return PhoneTools.result(true).put("memories", matches)
            }
            else -> return PhoneTools.result(false, "Ação de memória desconhecida.")
        }
    }
    @Synchronized fun tasks(context: Context, action: String, args: JSONObject): JSONObject {
        val entries = read(context, "tasks")
        if (action == "list") return PhoneTools.result(true).put("tasks", JSONArray().apply {
            for (i in 0 until entries.length()) entries.getJSONObject(i).let { if (args.optBoolean("include_done") || !it.optBoolean("done")) put(it) }
        })
        if (action == "add") {
            val title = args.optString("title").trim()
            require(title.length in 1..500 && entries.length() < 200) { "Informe uma tarefa de até 500 caracteres; limite de 200 tarefas." }
            val due = args.optString("due").trim()
            val timestamp = if (due.isEmpty()) 0L else OffsetDateTime.parse(due).toInstant().toEpochMilli().also {
                require(it > System.currentTimeMillis()) { "O lembrete precisa estar no futuro, com data, hora e fuso." }
            }
            val item = JSONObject().put("id", UUID.randomUUID().toString()).put("title", title).put("due", due)
                .put("due_ms", timestamp).put("done", false).put("notified", false)
            entries.put(item); write(context, "tasks", entries); TaskReminders.schedule(context, item)
            return PhoneTools.result(true).put("task", item).put("notifications_enabled", TaskReminders.enabled(context))
                .put("timing", "Lembretes aproximados; o Android pode adiar a notificação para economizar bateria.")
        }
        require(action in listOf("complete", "delete")) { "Ação de tarefa desconhecida." }
        val id = args.optString("id")
        val index = (0 until entries.length()).firstOrNull { entries.getJSONObject(it).getString("id") == id }
            ?: return PhoneTools.result(false, "Tarefa não encontrada; liste antes de escolher o ID.")
        if (action == "delete") entries.remove(index) else entries.getJSONObject(index).put("done", true)
        write(context, "tasks", entries); TaskReminders.cancel(context, id)
        return PhoneTools.result(true)
    }
}
