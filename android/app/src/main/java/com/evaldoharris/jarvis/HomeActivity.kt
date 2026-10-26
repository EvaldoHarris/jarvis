package com.evaldoharris.jarvis

import android.app.AlertDialog
import android.content.Intent
import android.os.Bundle
import android.widget.*
import org.json.JSONObject
import java.util.UUID

class HomeActivity : FeatureActivity() {
    override fun onCreate(savedInstanceState:Bundle?) { super.onCreate(savedInstanceState); render() }
    private fun render() {
        column.removeAllViews(); line("CASA — CÂMERAS E LUZES")
        button("VOLTAR AO JARVIS"){finish()}
        button("IMPORTAR CONFIGURAÇÕES DO PC PAREADO"){
            AlertDialog.Builder(this).setTitle("Copiar configurações da casa?")
                .setMessage("Copia para o armazenamento criptografado deste celular os endereços e credenciais das câmeras e da Tuya configurados no PC. Depois, o celular acessa esses serviços diretamente, sem depender do PC.")
                .setPositiveButton("Importar"){_,_-> worker.execute{
                    val result=runCatching{HomeConfig.importPc(this,PcClient(this).pairedPost("/api/android/home-config"))}
                    ui.post{if(!isFinishing)result.onSuccess{render();line("Configurações importadas. Confira canais e a conexão de rede de cada câmera.")}.onFailure{error(it)}}
                }}.setNegativeButton("Cancelar",null).show()
        }
        line("Câmeras: rede local ou VPN até a rede delas. RTSP usa a porta 554, não a porta TCP 37777 do aplicativo Intelbras. Vídeo H.264; áudio começa desligado.")
        button("ADICIONAR CÂMERA / DVR"){editCamera(null)}
        val cameras=CameraTools.list(this)
        for(i in 0 until cameras.length())cameras.getJSONObject(i).let{camera->
            button(camera.getString("name")){
                AlertDialog.Builder(this).setTitle(camera.getString("name")).setItems(arrayOf("Abrir canal ao vivo","Editar configuração","Remover do celular")){_,choice->
                    when(choice){
                        0->chooseChannel(camera)
                        1->editCamera(camera)
                        2->{val updated=CameraTools.list(this);val index=(0 until updated.length()).firstOrNull{updated.getJSONObject(it).getString("id")==camera.getString("id")};if(index!=null)updated.remove(index);PersonalData.write(this,"home_cameras",updated);render()}
                    }
                }.show()
            }
        }
        button("CONFIGURAR TUYA / SMART LIFE"){tuyaSettings()}
        button("LISTAR LUZES / DISPOSITIVOS TUYA"){
            line("Consultando Tuya…")
            worker.execute{
                val result=runCatching{TuyaClient(this).execute("list",JSONObject())}
                ui.post{if(!isFinishing)result.onSuccess{value->
                    val devices=value.getJSONArray("devices")
                    if(devices.length()==0)line("Nenhum dispositivo vinculado ao projeto Tuya.")
                    for(i in 0 until devices.length())devices.getJSONObject(i).let{device->
                        button(device.getString("name")){
                            AlertDialog.Builder(this).setTitle(device.getString("name")).setItems(arrayOf("Consultar estado","Ligar","Desligar","Ajustar brilho")){_,choice->
                                if(choice==3){val pick=NumberPicker(this).apply{minValue=1;maxValue=100;this.value=50};AlertDialog.Builder(this).setTitle("Brilho (%)").setView(pick).setPositiveButton("Aplicar"){_,_->light("brightness",device.getString("id"),pick.value)}.setNegativeButton("Cancelar",null).show()}
                                else light(listOf("status","on","off")[choice],device.getString("id"))
                            }.show()
                        }
                    }
                }.onFailure{error(it)}}
            }
        }
    }
    private fun light(action:String,name:String,percent:Int=100){
        worker.execute{val result=runCatching{TuyaClient(this).execute(action,JSONObject().put("name",name).put("percent",percent))};ui.post{if(!isFinishing)result.onSuccess{value->
            val message=if(action=="status"){
                val state=value.optJSONObject("status")?:JSONObject()
                val code=listOf("switch_led","switch_1","switch","led_switch").firstOrNull{state.has(it)}
                val power=if(code==null)"Sem estado de luz disponível." else if(state.optBoolean(code))"Ligada." else "Desligada."
                val bright=when{state.has("bright_value_v2")->((state.optInt("bright_value_v2")-10)*100/990).coerceIn(1,100);state.has("bright_value")->((state.optInt("bright_value")-25)*100/230).coerceIn(1,100);else->null}
                (if(value.optBoolean("online"))"" else "Offline — último estado conhecido: ")+power+(bright?.let{" Brilho: $it%."}?:"")
            } else if(value.optBoolean("verified"))"Alteração confirmada na consulta à Tuya." else "Comando aceito; o estado ainda não confirmou a mudança."
            AlertDialog.Builder(this).setTitle("Tuya").setMessage(message).setPositiveButton("OK",null).show()
        }.onFailure{error(it)}}}
    }
    private fun chooseChannel(camera:JSONObject){
        val pick=NumberPicker(this).apply{minValue=1;maxValue=camera.optInt("channel_count",64);value=camera.optInt("channel",1)}
        AlertDialog.Builder(this).setTitle("Canal do DVR / câmera").setView(pick).setPositiveButton("Abrir"){_,_->
            startActivity(Intent(this,CameraActivity::class.java).putExtra("camera_id",camera.getString("id")).putExtra("channel",pick.value))
        }.setNegativeButton("Cancelar",null).show()
    }
    private fun editCamera(old:JSONObject?){
        val camera=old?:JSONObject()
        val form=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL}
        val name=field(form,"Nome da câmera / DVR",camera.optString("name"))
        val host=field(form,"IP privado",camera.optString("host"))
        val vendor=Spinner(this).apply{adapter=ArrayAdapter(this@HomeActivity,android.R.layout.simple_spinner_dropdown_item,arrayOf("intelbras","icsee"));setSelection(if(camera.optString("vendor")=="icsee")1 else 0);form.addView(this)}
        val username=field(form,"Usuário do dispositivo",camera.optString("username"))
        val password=field(form,"Senha do dispositivo",camera.optString("password"),true)
        val port=field(form,"Porta RTSP",camera.optInt("port",554).toString())
        val count=field(form,"Quantidade de canais",camera.optInt("channel_count",16).toString())
        val channel=field(form,"Canal inicial",camera.optInt("channel",1).toString())
        val stream=Spinner(this).apply{adapter=ArrayAdapter(this@HomeActivity,android.R.layout.simple_spinner_dropdown_item,arrayOf("Principal","Substream (menos dados)"));setSelection(camera.optInt("stream",1));form.addView(this)}
        AlertDialog.Builder(this).setTitle("Câmera / DVR").setView(ScrollView(this).apply{addView(form)}).setPositiveButton("Salvar"){_,_->
            runCatching{
                HomeConfig.save(this,JSONObject().put("id",camera.optString("id").ifEmpty{UUID.randomUUID().toString()}).put("name",name.text.toString()).put("host",host.text.toString().trim())
                    .put("vendor",vendor.selectedItem.toString()).put("username",username.text.toString()).put("password",password.text.toString())
                    .put("port",port.text.toString().toInt()).put("channel_count",count.text.toString().toInt()).put("channel",channel.text.toString().toInt()).put("stream",stream.selectedItemPosition));render()
            }.onFailure{error(it)}
        }.setNegativeButton("Cancelar",null).show()
    }
    private fun tuyaSettings(){
        val store=SecureStore(this);val form=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL}
        val key=field(form,"Access ID",store.get("tuya_key"),true);val secret=field(form,"Access Secret",store.get("tuya_secret"),true)
        val regions=arrayOf("us","us-e","eu","eu-w","cn","in")
        val region=Spinner(this).apply{adapter=ArrayAdapter(this@HomeActivity,android.R.layout.simple_spinner_dropdown_item,regions);setSelection(regions.indexOf(store.get("tuya_region","us")).coerceAtLeast(0));form.addView(this)}
        AlertDialog.Builder(this).setTitle("Tuya / Smart Life").setView(form).setPositiveButton("Salvar"){_,_->store.put("tuya_key",key.text.toString().trim());store.put("tuya_secret",secret.text.toString().trim());store.put("tuya_region",region.selectedItem.toString())}.setNegativeButton("Cancelar",null).show()
    }
}
