package com.evaldoharris.jarvis

object VoiceInputPolicy {
    fun retryDisconnected(error: Int, alreadyRetried: Boolean): Boolean = error == 11 && !alreadyRetried
    fun message(error: Int): String = when (error) {
        1, 2 -> "O reconhecimento de voz não conseguiu acessar a rede. Confira a conexão e tente novamente."
        3 -> "O Android não conseguiu abrir o microfone. Feche outro aplicativo que esteja gravando áudio."
        6, 7 -> "Não entendi a fala. Toque em FALAR e tente novamente."
        8 -> "O serviço de voz está ocupado. Aguarde um instante e tente novamente."
        9 -> "Permita o microfone para o JARVIS nas configurações do Android."
        11 -> "O serviço de voz do Android desconectou. Tente o reconhecimento do sistema ou atualize o serviço de voz do Google."
        12, 13 -> "Português não está disponível no serviço de voz. Baixe o idioma português nas configurações de reconhecimento do Android."
        else -> "O serviço de voz não concluiu o reconhecimento (código $error). Tente novamente."
    }
}
