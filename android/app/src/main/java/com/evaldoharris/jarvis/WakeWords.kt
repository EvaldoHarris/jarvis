package com.evaldoharris.jarvis

import java.text.Normalizer

internal object WakeWords {
    private val variants=setOf("jarvis","jarves","jervis","javis","javes","djarvis","jarbas","jarbis","jarbes","jarvas","jarvi","jarviz","jarvys","garvis","harvis","xarvis","xarves","djavis","jarviss","jaarvis")
    private val greetings=setOf("ei","oi","ola","hey","ok","o","ô","oh","ai","e","fala","alo","eai","hei","ola","bom","dia","boa","tarde","noite")
    // Palavras comuns parecidas com Jarvis que nunca devem ativar o assistente.
    private val blocked=setOf("java","javas","chave","chaves","javier","jardim","jardins","javali","jarra","jarras","garras","garra","carros","harris","avisa","aviso","avisar","jovens","jarro","servis","service","servico","nervos","xavier","gavis","davis","travis","marvis","jairo","jarros")
    private fun normalize(text:String)=Normalizer.normalize(text,Normalizer.Form.NFD).replace(Regex("\\p{M}"),"").lowercase(java.util.Locale.ROOT).replace(Regex("[-'’]"),"")
    private fun distance(a:String,b:String):Int {
        val row=IntArray(b.length+1){it}
        for(i in 1..a.length){
            var previous=row[0];row[0]=i
            for(j in 1..b.length){
                val saved=row[j]
                row[j]=minOf(row[j]+1,row[j-1]+1,previous+if(a[i-1]==b[j-1])0 else 1)
                previous=saved
            }
        }
        return row[b.length]
    }
    /** Aceita grafias que o reconhecedor costuma produzir para "Jarvis". */
    private fun sounds(word:String):Boolean {
        if(word in blocked)return false
        if(word in variants)return true
        if(word.length !in 5..8 || word[0] !in "jdgxh")return false
        val d=distance(word,"jarvis")
        return d<=1 || (d==2 && Regex(".*(v|b|rv)[iey]?[sz]+$").matches(word))
    }
    fun validateAlias(value:String):String {
        val alias=value.trim()
        require(alias.matches(Regex("[\\p{L}'’-]{4,20}"))){"Use uma única palavra de 4 a 20 letras. Diga apenas Jarvis, sem o pedido."}
        require(normalize(alias) !in setOf("java","chave","chaves","jarbas","javier","aviso","avisar","servico","obrigado","certo","pronto","olha","voce","para")){
            "O Android reconheceu uma palavra comum ou outro nome. Tente dizer Jarvis novamente para evitar ativações por engano."
        }
        return alias
    }
    fun match(text:String,alias:String=""):IntRange? {
        val words=Regex("\\p{L}+(?:[-'’]\\p{L}+)*").findAll(text).toList()
        var index=0
        while(index<minOf(3,words.size)&&normalize(words[index].value) in greetings)index++
        val token=words.getOrNull(index)?:return null
        val normalized=normalize(token.value)
        if(sounds(normalized) || (alias.isNotBlank()&&normalized==normalize(alias)))return token.range
        // Palavra partida em duas: "jar vis", "ja vis", "dja ves".
        val next=words.getOrNull(index+1)?.value?.let{normalize(it)}
        if(normalized in setOf("jar","ja","dja","djar","gar") && next!=null && next in setOf("vis","ves","viz","vys","bis"))return token.range.first..words[index+1].range.last
        return null
    }
    /** Remove saudações e uma palavra com som de "Jarvis" do começo de um pedido já armado. */
    fun stripLeading(text:String):String {
        var rest=text.trim()
        repeat(4){
            val word=Regex("^\\p{L}+(?:[-'’]\\p{L}+)*").find(rest)?:return rest
            val n=normalize(word.value)
            if(n in greetings||sounds(n)||n in setOf("chaves","chave","jarbas","harvey","ja","vis","jair"))
                rest=rest.substring(word.range.last+1).trim(' ',',','.',':','!','?')
            else return rest
        }
        return rest
    }
    fun bias(alias:String="")=arrayListOf("Jarvis","Járvis","Djarvis","Olá Jarvis","Ei Jarvis","Oi Jarvis","Jarvis abra","Jarvis toque","Jarvis que horas são").apply{if(alias.isNotBlank())add(alias)}
    fun choose(candidates:List<String>,scores:FloatArray?,alias:String=""):String {
        val first=candidates.firstOrNull().orEmpty()
        if(match(first,alias)!=null)return first
        val plain=normalize(first).replace(Regex("[^\\p{L}\\s]")," ").trim().replace(Regex("\\s+")," ")
            .replace(Regex("^(?:(?:ei|oi|ola|hey|ok|o)\\s+){0,2}"),"")
        if(setOf("ja vi","java","chaves","javier","jardim","javali").any{plain==it||plain.startsWith("$it ")})return first
        val firstScore=scores?.getOrNull(0)?.takeIf{it in 0f..1f}
        for(index in 1 until minOf(5,candidates.size)){
            if(match(candidates[index],alias)==null)continue
            // Sem notas de confiança, só confiamos nas duas primeiras alternativas.
            if(firstScore==null){ if(index<=2)return candidates[index]; continue }
            val score=scores?.getOrNull(index)?:continue
            if(score>=.5f&&score>=firstScore-.25f)return candidates[index]
        }
        return first
    }
}
