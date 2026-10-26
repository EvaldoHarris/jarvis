package com.evaldoharris.jarvis

import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit

object MobileBrowser {
    @Volatile internal var current: BrowserActivity? = null
    private val main = Handler(Looper.getMainLooper())
    private fun <T> ui(action: () -> T): T {
        val future = CompletableFuture<T>()
        main.post { try { future.complete(action()) } catch (e: Exception) { future.completeExceptionally(e) } }
        return future.get(8, TimeUnit.SECONDS)
    }
    private fun browser(context: Context): BrowserActivity {
        if (current?.foreground != true) {
            ui { context.startActivity(Intent(context, BrowserActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)) }
            val deadline = System.currentTimeMillis() + 5000
            while (current?.foreground != true && System.currentTimeMillis() < deadline) Thread.sleep(50)
        }
        return current?.takeIf { it.foreground } ?: error("Abra o NAVEGADOR no JARVIS; o Android bloqueou sua abertura em segundo plano.")
    }
    private fun js(activity: BrowserActivity, script: String): JSONObject {
        val future = CompletableFuture<JSONObject>()
        main.post { activity.evaluate(script) { future.complete(it) } }
        return future.get(8, TimeUnit.SECONDS)
    }
    private fun inspect(activity: BrowserActivity): JSONObject {
        val deadline = System.currentTimeMillis() + 12000
        while (activity.loading && System.currentTimeMillis() < deadline) Thread.sleep(100)
        if (activity.failure.isNotEmpty()) return PhoneTools.result(false, activity.failure)
        if (activity.loading) return PhoneTools.result(false, "A página continua carregando; inspecione novamente antes de agir.")
        // Request a fresh DOM and matching visible viewport after navigation/interaction.
        val result = js(activity, """
            const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&r.bottom>0&&r.right>0&&r.top<innerHeight&&r.left<innerWidth&&s.visibility!=='hidden'&&s.display!=='none'};
            const label=e=>(e.innerText||e.getAttribute('aria-label')||e.placeholder||e.title||'').trim().slice(0,200);
            const controls=Array.from(document.querySelectorAll('a[href],button,input,textarea,select,[role="button"]')).filter(visible).slice(0,100).map(e=>({text:label(e),tag:e.tagName.toLowerCase(),id:e.id,type:e.type||'',href:e.tagName==='A'?e.href:undefined,disabled:!!e.disabled}));
            const walker=document.createTreeWalker(document.body||document.documentElement,NodeFilter.SHOW_TEXT);
            let text='',n;while((n=walker.nextNode())&&text.length<12000){if(!['SCRIPT','STYLE','NOSCRIPT'].includes(n.parentElement.tagName)&&visible(n.parentElement))text+=' '+n.textContent.trim();}
            return {ok:true,url:location.href,title:document.title,visible_text:text.slice(0,12000),controls};
        """.trimIndent())
        if (result.optBoolean("ok")) result.put("image", ui { activity.picture() }).put("mime_type", "image/jpeg")
        result.put("history", ui { activity.history() })
        return result
    }
    fun execute(context: Context, action: String, args: JSONObject): JSONObject {
      return try {
        require(action in listOf("open", "search", "inspect", "links", "click", "type", "scroll", "back")) { "Ação de navegador desconhecida." }
        val url = when (action) { "open" -> BrowserAddress.normalize(args.optString("url")); "search" -> BrowserAddress.search(args.optString("text")); else -> null }
        val activity = browser(context)
        when (action) {
            "open", "search" -> ui { activity.navigate(url!!) }
            "back" -> ui { check(activity.previousPage()) { "Não há página anterior." } }
            "scroll" -> ui {
                val direction = args.optString("direction", "down")
                require(direction in listOf("up", "down")) { "Direção deve ser up ou down." }
                activity.web.scrollBy(0, (activity.web.height * .75 * if (direction == "up") -1 else 1).toInt())
            }
            "click", "type" -> {
                val text = args.optString("text")
                val id = args.optString("id")
                require(text.isNotBlank() || id.isNotBlank()) { "Escolha um texto ou id observado na página." }
                val result = js(activity, """
                    const wanted=${JSONObject.quote(text)},id=${JSONObject.quote(id)},action=${JSONObject.quote(action)};
                    const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth&&getComputedStyle(e).visibility!=='hidden'};
                    const label=e=>(e.innerText||e.getAttribute('aria-label')||e.placeholder||e.title||'').trim();
                    let candidates=Array.from(document.querySelectorAll(action==='type'?'input,textarea':'a[href],button,input,[role="button"]')).filter(visible);
                    if(id)candidates=candidates.filter(e=>e.id===id);else{const exact=candidates.filter(e=>label(e).toLowerCase()===wanted.toLowerCase());candidates=exact.length?exact:candidates.filter(e=>label(e).toLowerCase().includes(wanted.toLowerCase()));}
                    if(candidates.length!==1)return {ok:false,error:'Controle ausente ou ambíguo; inspecione a página.',matches:candidates.length};
                    const e=candidates[0];if(e.disabled)return {ok:false,error:'Controle desativado.'};
                    if(action==='type'){
                        if((e.type||'').toLowerCase()==='password')return {ok:false,error:'Digite a senha pessoalmente.'};
                        const value=${JSONObject.quote(args.optString("value"))};
                        e.focus();const proto=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
                        const setter=Object.getOwnPropertyDescriptor(proto,'value').set;setter.call(e,value);e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));
                    }else{
                        if(e.tagName==='A'){const u=new URL(e.href,location.href);if(!['http:','https:'].includes(u.protocol)||u.username||u.password)return {ok:false,error:'Link não permitido.'};e.target='_self';}
                        e.click();
                    }
                    return {ok:true,action_dispatched:true};
                """.trimIndent())
                if (!result.optBoolean("ok")) return result
                Thread.sleep(450)
            }
        }
        inspect(activity)
      } catch (e: Exception) { PhoneTools.result(false, e.cause?.message ?: e.message ?: "Falha no navegador Android.") }
    }
}
