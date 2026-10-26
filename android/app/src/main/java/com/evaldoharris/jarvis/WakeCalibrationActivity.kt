package com.evaldoharris.jarvis

import android.Manifest
import android.app.AlertDialog
import android.content.pm.PackageManager
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.content.Intent
import android.widget.TextView

/** User initiated pronunciation calibration; no audio recording is saved. */
class WakeCalibrationActivity:FeatureActivity(){
    private var recognizer:SpeechRecognizer?=null
    private var active=false
    private var request=0
    private var candidate=""
    private lateinit var heard:TextView
    override fun onCreate(savedInstanceState:Bundle?){
        super.onCreate(savedInstanceState)
        line("AJUSTAR A PALAVRA JARVIS")
        line("Toque em OUVIR e diga apenas Jarvis uma vez, com sua pronúncia normal. Confira o que o Android entendeu antes de salvar. O app não salva gravações; o reconhecimento usa o serviço de voz do Android.")
        heard=line("Variação salva: "+SecureStore(this).get("wake_alias").ifBlank{"padrão"})
        button("OUVIR JARVIS"){listen()}
        button("SALVAR VARIAÇÃO"){
            runCatching{WakeWords.validateAlias(candidate)}.onSuccess{alias->
                AlertDialog.Builder(this).setTitle("Usar esta variação?").setMessage("O Android entendeu “$alias” quando você disse Jarvis. Essa palavra também poderá ativar o assistente. Jarvis continuará funcionando.")
                    .setPositiveButton("Salvar"){_,_->SecureStore(this).put("wake_alias",alias);heard.text="Variação salva: $alias"}
                    .setNegativeButton("Cancelar",null).show()
            }.onFailure{error(it)}
        }
        button("RESTAURAR RECONHECIMENTO PADRÃO"){SecureStore(this).put("wake_alias","");candidate="";heard.text="Reconhecimento padrão restaurado."}
        button("VOLTAR AO JARVIS"){finish()}
    }
    private fun listen(){
        if(active)return
        if(AppState.assistantBusy||AppState.expectedPhoneReply.isNotEmpty()){heard.text="Aguarde o pedido atual terminar ou interrompa-o no JARVIS antes de ajustar a pronúncia.";return}
        if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED){requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO),51);return}
        if(!SpeechRecognizer.isRecognitionAvailable(this)){heard.text="Habilite o serviço de reconhecimento de voz do Android.";return}
        candidate="";active=true;val current=++request
        GeminiVoice.stop();AppState.manualListening=true
        heard.text="Preparando o microfone…"
        ui.postDelayed({
            if(!active||request!=current||isFinishing||isDestroyed)return@postDelayed
            if(recognizer==null)recognizer=SpeechRecognizer.createSpeechRecognizer(this).apply{
                setRecognitionListener(object:RecognitionListener{
                    override fun onReadyForSpeech(params:Bundle?){if(active)heard.text="PODE FALAR: diga apenas Jarvis."}
                    override fun onResults(results:Bundle?){
                        if(!active)return
                        active=false
                        candidate=results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty().trim().trim('.',',','!','?')
                        heard.text=if(candidate.isBlank())"Nenhuma palavra reconhecida. Tente novamente." else "O Android entendeu: “$candidate”. Confira e toque em SALVAR VARIAÇÃO."
                    }
                    override fun onError(error:Int){if(active){active=false;heard.text=VoiceInputPolicy.message(error);if(error==11){recognizer?.destroy();recognizer=null}}}
                    override fun onBeginningOfSpeech()=Unit
                    override fun onRmsChanged(rmsdB:Float)=Unit
                    override fun onBufferReceived(buffer:ByteArray?)=Unit
                    override fun onEndOfSpeech()=Unit
                    override fun onPartialResults(partialResults:Bundle?)=Unit
                    override fun onEvent(eventType:Int,params:Bundle?)=Unit
                })
            }
            try{recognizer?.startListening(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE,"pt-BR").putExtra(RecognizerIntent.EXTRA_MAX_RESULTS,1))}
            catch(_:Exception){active=false;heard.text="O microfone não iniciou. Tente novamente."}
        },400)
    }
    override fun onRequestPermissionsResult(requestCode:Int,permissions:Array<out String>,grantResults:IntArray){
        super.onRequestPermissionsResult(requestCode,permissions,grantResults)
        if(requestCode==51&&grantResults.firstOrNull()==PackageManager.PERMISSION_GRANTED)listen()
    }
    override fun onStop(){active=false;request++;recognizer?.cancel();AppState.manualListening=false;super.onStop()}
    override fun onPause(){active=false;request++;recognizer?.cancel();AppState.manualListening=false;super.onPause()}
    override fun onResume(){super.onResume();AppState.manualListening=true}
    override fun onDestroy(){recognizer?.destroy();recognizer=null;super.onDestroy()}
}
