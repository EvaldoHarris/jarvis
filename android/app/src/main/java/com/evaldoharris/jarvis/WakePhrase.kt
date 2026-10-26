package com.evaldoharris.jarvis

class WakePhrase {
    private var alias=""
    fun configureAlias(value:String){if(alias!=value){reset();alias=value}}
    private var armedUntil = 0L
    private var partialWake = false
    fun preview(text:String,mode:String,now:Long):Boolean {
        if(mode!="wake" || partialWake || keyword(text.trim())==null)return false
        partialWake=true;arm(now);return true
    }
    fun arm(now:Long){armedUntil=now+10000}
    fun deadline()=armedUntil
    fun expectingFollowup(now:Long)=armed(now)&&!partialWake
    fun reset(){armedUntil=0;partialWake=false}
    private fun keyword(text:String)=WakeWords.match(text,alias)
    fun command(text: String, mode: String, now: Long): String? {
        val clean = text.trim()
        if(mode!="wake"){reset();return if(mode=="continuous")clean.takeIf{it.isNotBlank()}else null}
        val previewed=partialWake;partialWake=false
        val word=keyword(clean)
        if(word!=null){
            var rest=clean.substring((word.last+1).coerceAtMost(clean.length)).trim(' ',',','.',':','!','?')
            while(rest.isNotEmpty()){
                val repeated=keyword(rest)?:break
                rest=rest.substring(repeated.last+1).trim(' ',',','.',':','!','?')
            }
            if(rest.isBlank()){if(!previewed)arm(now);return null}
            armedUntil=0;return rest
        }
        // A provisional wake word corrected away in the final transcript is not a command.
        if(previewed){armedUntil=0;return null}
        if(now<armedUntil&&clean.isNotBlank()){
            // Armado pelo detector offline: o Google pode ter escrito o nome como "Chaves" ou "Jarbas".
            val rest=WakeWords.stripLeading(clean)
            if(rest.isBlank())return null
            armedUntil=0;return rest
        }
        return null
    }
    fun armed(now: Long) = now < armedUntil
}
