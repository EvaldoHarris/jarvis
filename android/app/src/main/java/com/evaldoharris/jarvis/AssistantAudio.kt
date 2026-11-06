package com.evaldoharris.jarvis

import android.media.AudioAttributes

/** Identical routing for Jarvis replies and translated narration. */
internal object AssistantAudio {
    fun attributes():AudioAttributes=AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ASSISTANT)
        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).setAllowedCapturePolicy(AudioAttributes.ALLOW_CAPTURE_BY_NONE).build()
}
