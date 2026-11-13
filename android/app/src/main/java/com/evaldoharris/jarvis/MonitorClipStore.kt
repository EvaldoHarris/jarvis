package com.evaldoharris.jarvis

import android.content.Context
import org.json.JSONObject
import java.io.*

/** Private app storage, 24 hours, 200 MB total, 50 MB per alert. */
internal object MonitorClipStore {
    data class Frame(val offset: Double, val position: Long, val size: Int)
    private var root: File? = null
    private fun valid(id: String) = id.matches(Regex("monitor_[a-f0-9]{24}"))
    fun init(context: Context) {
        if (root != null) return
        root = File(context.filesDir, "monitor_clips").apply { mkdirs() }
        prune()
    }
    fun prune() {
        val dir = root ?: return
        val groups = dir.listFiles()?.filter { valid(it.nameWithoutExtension) }?.groupBy { it.nameWithoutExtension } ?: return
        var total = groups.values.flatten().sumOf { it.length() }
        for ((_, files) in groups.entries.sortedBy { it.value.maxOf { file -> file.lastModified() } }) {
            if (System.currentTimeMillis() - files.maxOf { it.lastModified() } > 86400000L || total > 200000000L) {
                for (file in files) { val size = file.length(); if (file.delete()) total -= size }
            }
        }
    }
    fun begin(message: JSONObject) {
        val id = message.optString("alert_id")
        if (!valid(id)) return
        val dir = root ?: return
        val metadata = JSONObject().put("alert_id", id).put("group", message.optString("group").take(70))
            .put("camera", message.optString("camera").take(100)).put("time", message.optString("time").take(60))
        File(dir, "$id.json").writeText(metadata.toString())
    }
    fun append(id: String, offset: Double, bytes: ByteArray): Frame? {
        if (!valid(id) || bytes.isEmpty() || bytes.size > 700000 || !offset.isFinite()) return null
        val file = File(root ?: return null, "$id.frames")
        val position = file.length() + 12
        if (position + bytes.size > 50000000L) return null
        DataOutputStream(FileOutputStream(file, true)).use { it.writeDouble(offset); it.writeInt(bytes.size); it.write(bytes) }
        return Frame(offset, position, bytes.size)
    }
    fun read(id: String, frame: Frame): ByteArray? { return try {
        if (!valid(id) || frame.size !in 1..700000) null else {
            val file = File(root ?: return null, "$id.frames")
            RandomAccessFile(file, "r").use { stream -> stream.seek(frame.position); ByteArray(frame.size).also { stream.readFully(it) } }
        }
    } catch (_: IOException) { null } }
    fun list(): List<Pair<JSONObject, List<Frame>>> {
        val dir = root ?: return emptyList()
        prune()
        return dir.listFiles()?.filter { it.extension == "json" && valid(it.nameWithoutExtension) && it.length() < 10000 }
            ?.sortedByDescending { it.lastModified() }?.mapNotNull { metadata ->
                try {
                    val file = File(dir, "${metadata.nameWithoutExtension}.frames")
                    if (!file.exists() || file.length() > 50000000L) return@mapNotNull null
                    val frames = mutableListOf<Frame>()
                    RandomAccessFile(file, "r").use { stream ->
                        while (stream.filePointer + 12 <= stream.length()) {
                            val offset = stream.readDouble(); val size = stream.readInt()
                            if (!offset.isFinite() || size !in 1..700000 || stream.filePointer + size > stream.length()) break
                            frames.add(Frame(offset, stream.filePointer, size)); stream.seek(stream.filePointer + size)
                        }
                    }
                    JSONObject(metadata.readText()).put("alert_id", metadata.nameWithoutExtension) to frames
                } catch (_: Exception) { null }
            } ?: emptyList()
    }
}
