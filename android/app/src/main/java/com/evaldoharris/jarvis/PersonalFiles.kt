package com.evaldoharris.jarvis

import android.content.Context
import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.provider.OpenableColumns
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

object PersonalFiles {
    @Synchronized fun attach(context: Context, uri: Uri): JSONObject {
        require(uri.scheme == "content")
        var name = "Documento"
        context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use {
            if (it.moveToFirst()) name = it.getString(0).take(160)
        }
        val files = PersonalData.read(context, "documents")
        require(files.length() < 100) { "Limite de 100 documentos. Remova um vínculo antes de adicionar." }
        val id = UUID.randomUUID().toString()
        val item = JSONObject().put("id", id).put("name", name).put("uri", uri.toString()).put("mime", context.contentResolver.getType(uri) ?: "application/octet-stream")
        files.put(item); PersonalData.write(context, "documents", files)
        return JSONObject(item.toString()).apply { remove("uri") }
    }
    private fun public(item: JSONObject) = JSONObject(item.toString()).apply { remove("uri") }
    @Synchronized fun execute(context: Context, action: String, args: JSONObject): JSONObject {
        val files = PersonalData.read(context, "documents")
        if (action == "list") return PhoneTools.result(true).put("files", JSONArray().apply { for (i in 0 until files.length()) put(public(files.getJSONObject(i))) })
        if (action == "create") {
            val name = args.optString("name").trim()
            val text = args.optString("text")
            require(name.matches(Regex("[\\p{L}\\p{N}_ .-]{1,100}")) && name !in listOf(".", "..") && text.length <= 200000) { "Nome ou conteúdo inválido; use um nome simples e texto de até 200 mil caracteres." }
            require(files.length() < 100) { "Limite de documentos atingido." }
            val id = UUID.randomUUID().toString()
            // Generated notes remain encrypted; only an explicit export creates a plaintext copy.
            SecureStore(context).put("document_$id", text)
            val item = JSONObject().put("id", id).put("name", if (name.endsWith(".txt")) name else "$name.txt").put("mime", "text/plain").put("generated", true)
            files.put(item); PersonalData.write(context, "documents", files)
            return PhoneTools.result(true).put("file", public(item))
        }
        val id = args.optString("id")
        val item = (0 until files.length()).map { files.getJSONObject(it) }.firstOrNull { it.getString("id") == id }
            ?: return PhoneTools.result(false, "Documento não encontrado. Use list ou selecione um arquivo em MEMÓRIA E TAREFAS → ADICIONAR ARQUIVO.")
        if(action=="update"){
            require(item.optBoolean("generated")){"O original foi autorizado só para leitura. Use create para salvar uma nova cópia de texto."}
            val text=args.optString("text");require(text.length<=200000)
            SecureStore(context).put("document_$id",text)
            return PhoneTools.result(true).put("file",public(item))
        }
        if(action=="unlink"){
            val index=(0 until files.length()).first{files.getJSONObject(it).getString("id")==id}
            files.remove(index);PersonalData.write(context,"documents",files)
            if(item.optBoolean("generated")){
                SecureStore(context).put("document_$id","")
                File(context.cacheDir,"exports/$id.txt").delete()
            }else if((0 until files.length()).none{files.getJSONObject(it).optString("uri")==item.optString("uri")}){
                runCatching{context.contentResolver.releasePersistableUriPermission(Uri.parse(item.getString("uri")),android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION)}
            }
            return PhoneTools.result(true).put("original_deleted",false)
        }
        require(action == "read") { "Ação de arquivo desconhecida." }
        if (item.optBoolean("generated")) return PhoneTools.result(true).put("text", SecureStore(context).get("document_$id")).put("file", public(item))
        val uri = Uri.parse(item.getString("uri"))
        if (item.getString("mime") == "application/pdf" || item.getString("name").endsWith(".pdf", true)) {
            context.contentResolver.openFileDescriptor(uri, "r")!!.use { fd ->
                require(fd.statSize in 1..30_000_000) { "Selecione um PDF local com tamanho conhecido de até 30 MB." }
                PdfRenderer(fd).use { pdf ->
                    val page = args.optInt("page", 1)
                    require(page in 1..pdf.pageCount) { "Escolha uma página entre 1 e ${pdf.pageCount}." }
                    pdf.openPage(page - 1).use { value ->
                        val scale = minOf(1440.0 / value.width, 1920.0 / value.height)
                        val bitmap = Bitmap.createBitmap((value.width * scale).toInt().coerceAtLeast(1), (value.height * scale).toInt().coerceAtLeast(1), Bitmap.Config.ARGB_8888)
                        try {
                            bitmap.eraseColor(android.graphics.Color.WHITE)
                            value.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                            return PhoneTools.result(true).put("image", PhoneTools.encode(bitmap)).put("page", page).put("pages", pdf.pageCount).put("file", public(item))
                        } finally { bitmap.recycle() }
                    }
                }
            }
        }
        val mime = item.getString("mime")
        require(mime.startsWith("text/") || mime in listOf("application/json", "application/xml") || item.getString("name").substringAfterLast('.').lowercase() in listOf("txt", "md", "csv", "json", "log", "xml")) { "Leitura disponível para texto, CSV, JSON e PDF. Abra outros formatos no aplicativo correspondente." }
        val bytes = context.contentResolver.openInputStream(uri)!!.use { it.readBounded(1_000_000) }
        require(bytes.size <= 1_000_000) { "Texto maior que 1 MB; selecione um arquivo menor." }
        val text = bytes.toString(Charsets.UTF_8)
        val offset = args.optInt("offset", 0)
        require(offset in 0..text.length)
        return PhoneTools.result(true).put("text", text.substring(offset, minOf(text.length, offset + 20000)))
            .put("next_offset", if (offset + 20000 < text.length) offset + 20000 else JSONObject.NULL).put("file", public(item))
    }
    fun export(context: Context, item: JSONObject): File {
        require(item.optBoolean("generated"))
        val folder = File(context.cacheDir, "exports").apply { mkdirs() }
        return File(folder, item.getString("id") + ".txt").apply { writeText(SecureStore(context).get("document_${item.getString("id")}")) }
    }
}
