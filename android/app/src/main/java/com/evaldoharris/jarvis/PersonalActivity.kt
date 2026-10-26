package com.evaldoharris.jarvis

import android.app.AlertDialog
import android.app.DatePickerDialog
import android.app.TimePickerDialog
import android.content.Intent
import android.os.Bundle
import android.widget.LinearLayout
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.time.ZonedDateTime

class PersonalActivity : FeatureActivity() {
    override fun onCreate(savedInstanceState: Bundle?) { super.onCreate(savedInstanceState); render() }
    private fun render() {
        column.removeAllViews(); line("MEMÓRIA, ARQUIVOS E TAREFAS")
        button("VOLTAR AO JARVIS") { finish() }
        button("IMPORTAR MEMÓRIAS DO PC PAREADO") {
            AlertDialog.Builder(this).setTitle("Copiar memórias do PC?").setMessage("As informações serão copiadas para este celular com o prefixo PC. Alterações futuras não serão sincronizadas automaticamente.")
                .setPositiveButton("Importar"){_,_->worker.execute{
                    val result=runCatching{PersonalData.importMemories(this,PcClient(this).pairedPost("/api/android/memories"))}
                    ui.post{if(!isFinishing)result.onSuccess{render();line("$it informações importadas.")}.onFailure{error(it)}}
                }}.setNegativeButton("Cancelar",null).show()
        }
        line("Salvos neste celular. Para usar um arquivo por voz, adicione-o aqui e peça ao JARVIS para lê-lo.")
        button("NOVA MEMÓRIA") {
            val form=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL}
            val key=field(form,"Nome da informação"); val value=field(form,"O que lembrar")
            AlertDialog.Builder(this).setTitle("Lembrar informação").setView(form).setPositiveButton("Salvar") { _,_ ->
                runCatching { PersonalData.memory(this,"remember",JSONObject().put("key",key.text).put("value",value.text)); render() }.onFailure { error(it) }
            }.setNegativeButton("Cancelar",null).show()
        }
        val memories=PersonalData.read(this,"memories")
        for(i in 0 until memories.length()) memories.getJSONObject(i).let { item ->
            button("${item.getString("key")}: ${item.getString("value")}") {
                AlertDialog.Builder(this).setTitle(item.getString("key")).setMessage(item.getString("value"))
                    .setPositiveButton("Fechar",null).setNegativeButton("Esquecer") { _,_ -> PersonalData.memory(this,"forget",JSONObject().put("key",item.getString("key"))); render() }.show()
            }
        }
        button("NOVA TAREFA") { newTask() }
        if(!TaskReminders.enabled(this)) line("Notificações desativadas: habilite-as nas configurações do Android para receber lembretes.")
        val tasks=PersonalData.read(this,"tasks")
        for(i in 0 until tasks.length()) tasks.getJSONObject(i).let { task ->
            button((if(task.optBoolean("done")) "✓ " else "○ ")+task.getString("title")+task.optString("due").let { if(it.isEmpty()) "" else "\n"+runCatching { java.time.OffsetDateTime.parse(it).format(java.time.format.DateTimeFormatter.ofPattern("dd/MM/yyyy HH:mm")) }.getOrDefault(it) }) {
                AlertDialog.Builder(this).setTitle(task.getString("title")).setItems(arrayOf("Concluir","Excluir tarefa")) { _,index ->
                    PersonalData.tasks(this,if(index==0)"complete" else "delete",JSONObject().put("id",task.getString("id"))); render()
                }.setNegativeButton("Cancelar",null).show()
            }
        }
        button("ADICIONAR ARQUIVO") { startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION),41) }
        val files=PersonalData.read(this,"documents")
        for(i in 0 until files.length()) files.getJSONObject(i).let { item ->
            button(item.getString("name")) {
                if(item.optBoolean("generated")) AlertDialog.Builder(this).setTitle(item.getString("name")).setItems(arrayOf("Ler","Compartilhar cópia")) { _,choice ->
                    if(choice==1) {
                        val file=PersonalFiles.export(this,item)
                        val uri=FileProvider.getUriForFile(this,"$packageName.files",file)
                        startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_STREAM,uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION),"Compartilhar documento"))
                    } else readFile(item)
                }.show() else readFile(item)
            }.setOnLongClickListener {
                AlertDialog.Builder(this).setTitle("Remover da biblioteca?").setMessage("Remove o vínculo no JARVIS. O arquivo original selecionado não será excluído.")
                    .setPositiveButton("Remover"){_,_->PersonalFiles.execute(this,"unlink",JSONObject().put("id",item.getString("id")));render()}.setNegativeButton("Cancelar",null).show();true
            }
        }
    }
    private fun readFile(item: JSONObject) {
        worker.execute {
            val result=runCatching { PersonalFiles.execute(this,"read",JSONObject().put("id",item.getString("id"))) }
            ui.post { if(!isFinishing) result.onSuccess { value ->
                if(value.has("image")) {
                    val bytes=android.util.Base64.decode(value.getString("image"),android.util.Base64.NO_WRAP)
                    val preview=android.widget.ImageView(this).apply{setImageBitmap(android.graphics.BitmapFactory.decodeByteArray(bytes,0,bytes.size));adjustViewBounds=true}
                    AlertDialog.Builder(this).setTitle("Página 1 — ${item.getString("name")}").setView(android.widget.ScrollView(this).apply{addView(preview)}).setPositiveButton("Fechar",null).show()
                } else AlertDialog.Builder(this).setTitle(item.getString("name")).setMessage(value.optString("text").take(20000)).setPositiveButton("Fechar",null).show()
            }.onFailure { error(it) } }
        }
    }
    private fun newTask() {
        val form=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL }
        val title=field(form,"O que fazer")
        AlertDialog.Builder(this).setTitle("Nova tarefa").setView(form)
            .setPositiveButton("Sem lembrete") { _,_ -> saveTask(title.text.toString(),"") }
            .setNeutralButton("Escolher lembrete") { _,_ ->
                val now=ZonedDateTime.now()
                DatePickerDialog(this,{ _,year,month,day ->
                    TimePickerDialog(this,{ _,hour,minute ->
                        val date=java.time.LocalDateTime.of(year,month+1,day,hour,minute).atZone(java.time.ZoneId.systemDefault()).toOffsetDateTime()
                        saveTask(title.text.toString(),date.toString())
                    },now.hour,now.minute,true).show()
                },now.year,now.monthValue-1,now.dayOfMonth).show()
            }.setNegativeButton("Cancelar",null).show()
    }
    private fun saveTask(title:String,due:String) { runCatching { PersonalData.tasks(this,"add",JSONObject().put("title",title).put("due",due)); render() }.onFailure{error(it)} }
    override fun onActivityResult(requestCode:Int,resultCode:Int,data:Intent?) {
        super.onActivityResult(requestCode,resultCode,data)
        if(requestCode==41&&resultCode==RESULT_OK) data?.data?.let { uri ->
            runCatching {
                contentResolver.takePersistableUriPermission(uri,Intent.FLAG_GRANT_READ_URI_PERMISSION)
                PersonalFiles.attach(this,uri); render()
            }.onFailure { error(it) }
        }
    }
}
