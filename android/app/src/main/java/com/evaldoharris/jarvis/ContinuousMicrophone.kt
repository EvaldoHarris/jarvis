package com.evaldoharris.jarvis

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.ParcelFileDescriptor
import java.io.Closeable

/** One capture per listening session. Muting discards audio, without reopening the mic. */
internal class ContinuousMicrophone(private val muted: () -> Boolean, private val onAudio: ((ByteArray, Int) -> Unit)? = null) : Closeable {
    private val pipe = ParcelFileDescriptor.createPipe()
    val source: ParcelFileDescriptor get() = pipe[0]
    private val output = ParcelFileDescriptor.AutoCloseOutputStream(pipe[1])
    @Volatile private var closed = false
    private var recorder: AudioRecord? = null

    @SuppressLint("MissingPermission")
    fun start(onFailure: () -> Unit) {
        val size = maxOf(6400, AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT))
        val audio = AudioRecord.Builder().setAudioSource(MediaRecorder.AudioSource.VOICE_RECOGNITION)
            .setAudioFormat(AudioFormat.Builder().setSampleRate(16000).setChannelMask(AudioFormat.CHANNEL_IN_MONO)
                .setEncoding(AudioFormat.ENCODING_PCM_16BIT).build()).setBufferSizeInBytes(size).build()
        recorder = audio
        check(audio.state == AudioRecord.STATE_INITIALIZED)
        audio.startRecording()
        Thread({
            try {
                val buffer = ByteArray(3200)
                while (!closed) {
                    val count = audio.read(buffer, 0, buffer.size)
                    if (closed) break
                    check(count > 0)
                    if (muted()) buffer.fill(0, 0, count)
                    else onAudio?.let { listener -> runCatching { listener(buffer, count) } }
                    output.write(buffer, 0, count)
                }
            } catch (_: Exception) { if (!closed) onFailure() }
        }, "jarvis-continuous-microphone").start()
    }

    override fun close() {
        closed = true
        runCatching { source.close() }
        runCatching { output.close() }
        recorder?.let { runCatching { it.stop() }; it.release() }
        recorder = null
    }
}
