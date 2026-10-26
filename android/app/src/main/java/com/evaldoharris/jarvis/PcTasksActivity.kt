package com.evaldoharris.jarvis

import android.os.Bundle
import org.json.JSONObject
import okhttp3.Request

class PcTasksActivity : FeatureActivity() {
    private var plan: JSONObject? = null
    private val loading = java.util.concurrent.atomic.AtomicBoolean(false)
    private lateinit var status: android.widget.TextView
    private val poll = object : Runnable { override fun run() { refresh(); ui.postDelayed(this, 2500) } }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        line("TAREFAS DO PC")
        line("Acompanhe o plano do computador pareado. O PC precisa estar conectado; o restante do app continua independente.")
        status=line("Conectando…")
        button("PAUSAR") { change("pause") }
        button("CONTINUAR") { change("resume") }
        button("CANCELAR TAREFA") { change("cancel") }
        button("ATUALIZAR") { refresh() }
    }
    override fun onResume() { super.onResume(); ui.post(poll) }
    override fun onPause() { ui.removeCallbacks(poll); super.onPause() }
    private fun show(data: JSONObject) {
        plan=data.optJSONObject("plan")
        status.text=plan?.let { p -> buildString {
            val states=mapOf("active" to "Em andamento","paused" to "Pausada","blocked" to "Bloqueada","completed" to "Concluída","cancelled" to "Cancelada")
            append(p.optString("objective")); append("\n${p.optInt("completed")}/${p.optInt("total")} — ${states[p.optString("state")] ?: p.optString("state")}\n\n")
            val steps=p.getJSONArray("steps")
            for(i in 0 until steps.length()) { val s=steps.getJSONObject(i); append(if(s.optString("state")=="done") "✓ " else "○ ");append(s.optString("title"));append('\n') }
            append(p.optString("reason"))
        } } ?: "Nenhuma tarefa registrada no PC."
    }
    private fun refresh() { if(!loading.compareAndSet(false,true)) return; worker.execute {
        runCatching {
            val pc=PcClient(this)
            fun get(token:String): JSONObject {
                pc.client.newCall(Request.Builder().url(pc.address()+"/api/tasks").header("Authorization","Bearer $token").build()).execute().use { response ->
                    if(response.code==401) throw PcClient.Unauthorized()
                    check(response.isSuccessful) { "PC indisponível (HTTP ${response.code})" }
                    return JSONObject(response.body?.string() ?: "{}")
                }
            }
            val token=pc.store.get("pc_token").ifEmpty { pc.renew() }
            try { get(token) } catch (_: PcClient.Unauthorized) { get(pc.renew()) }
        }.onSuccess { data -> ui.post { show(data) } }.onFailure { e -> ui.post { status.text=e.message ?: "PC desconectado" } }
        loading.set(false)
    } }
    private fun change(action:String) {
        val current=plan ?: return
        worker.execute {
            runCatching { PcClient(this).pairedPost("/api/tasks",JSONObject().put("action",action).put("plan_id",current.getString("id")).put("revision",current.getInt("revision"))) }
                .onSuccess { data -> ui.post { show(data) } }.onFailure { e -> ui.post { error(e) } }
        }
    }
}
