package com.evaldoharris.jarvis

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.net.Socket
import java.net.URI
import java.security.*
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.security.spec.ECGenParameterSpec
import java.util.UUID
import java.util.concurrent.TimeUnit
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec
import javax.net.ssl.*

/** Keys stay in Android Keystore. No insecure hostname verifier or trust-all manager. */
object DirectChannel {
    private fun b64(bytes: ByteArray) = Base64.encodeToString(bytes, Base64.NO_WRAP)
    private fun un64(value: String) = Base64.decode(value, Base64.DEFAULT)
    private fun hex(bytes: ByteArray) = bytes.joinToString("") { "%02x".format(it) }
    private fun digest(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes)
    private fun certificate(value: String) = CertificateFactory.getInstance("X.509").generateCertificate(value.byteInputStream()) as X509Certificate
    private fun keyStore() = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
    private fun sign(alias: String, value: ByteArray): ByteArray = Signature.getInstance("SHA256withECDSA").run {
        initSign(keyStore().getKey(alias, null) as PrivateKey); update(value); sign()
    }
    private fun crypt(key: ByteArray, nonce: ByteArray, data: ByteArray, aad: String, encrypt: Boolean): ByteArray = Cipher.getInstance("AES/GCM/NoPadding").run {
        init(if (encrypt) Cipher.ENCRYPT_MODE else Cipher.DECRYPT_MODE, SecretKeySpec(key, "AES"), GCMParameterSpec(128, nonce))
        updateAAD(aad.toByteArray()); doFinal(data)
    }
    @Synchronized fun enroll(context: Context, raw: String) {
        val encoded = raw.trim().removePrefix("jarvis-direct:")
        val decoded = if (encoded.startsWith("z:")) {
            val packed = Base64.decode(encoded.removePrefix("z:"), Base64.URL_SAFE or Base64.NO_WRAP)
            java.util.zip.InflaterInputStream(packed.inputStream()).use { stream ->
                val bytes = stream.readNBytes(16001)
                require(bytes.size <= 16000) { "Convite muito grande" }
                bytes
            }
        } else Base64.decode(encoded, Base64.URL_SAFE or Base64.NO_WRAP)
        val ticket = JSONObject(String(decoded, Charsets.UTF_8))
        require(ticket.getInt("v") == 1 && ticket.getLong("expires") > System.currentTimeMillis() / 1000) { "Convite expirado. Gere outro no PC." }
        val enroll = URI(ticket.getString("enroll"))
        require(enroll.scheme == "http" && enroll.path == "/api/direct/enroll" && enroll.query == null && enroll.fragment == null)
        ServerAddress.normalize("${enroll.scheme}://${enroll.rawAuthority}") // Local/VPN HTTP only; ticket secret never goes onto the wire.
        val direct = ServerAddress.normalize(ticket.getString("url")); require(direct.startsWith("https://"))
        if (!ticket.has("ca")) {
            val fingerprint = ticket.getString("ca_sha256")
            require(fingerprint.matches(Regex("[0-9a-f]{64}"))) { "Convite inválido" }
            val bootstrap = OkHttpClient.Builder().connectTimeout(6, TimeUnit.SECONDS).readTimeout(10, TimeUnit.SECONDS).followRedirects(false).build()
            val ca = bootstrap.newCall(Request.Builder().url(enroll.resolve("/api/direct/ca").toString()).build()).execute().use {
                check(it.isSuccessful) { "Atualize e reinicie o Jarvis do PC para ler este convite (HTTP ${it.code})." }
                val bytes = it.body?.byteStream()?.readNBytes(8193) ?: error("Certificado indisponível")
                require(bytes.size <= 8192)
                JSONObject(String(bytes, Charsets.UTF_8)).getString("ca")
            }
            require(hex(digest(ca.toByteArray(Charsets.UTF_8))) == fingerprint) { "O certificado recebido não corresponde ao QR. Pareamento bloqueado." }
            ticket.put("ca", ca)
        }
        val root = certificate(ticket.getString("ca")); root.checkValidity(); root.verify(root.publicKey); require(root.basicConstraints >= 0)
        val secret = un64(ticket.getString("secret")); require(secret.size == 32)
        val token = hex(digest(secret))
        val store = SecureStore(context)
        var pending = runCatching { JSONObject(store.get("direct_pending", "{}")) }.getOrDefault(JSONObject())
        if (pending.optString("ticket") != token) {
            val id = UUID.randomUUID().toString(); val alias = "jarvis_direct_$id"
            val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore")
            generator.initialize(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
                .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1")).setDigests(KeyProperties.DIGEST_SHA256, KeyProperties.DIGEST_NONE).build())
            val public = generator.generateKeyPair().public.encoded
            val payload = JSONObject().put("id", id).put("name", android.os.Build.MODEL).put("public", b64(public))
                .put("proof", b64(sign(alias, "jarvis-enroll\n$id\n${hex(digest(public))}".toByteArray())))
            val nonce = ByteArray(12).also { SecureRandom().nextBytes(it) }
            val sealed = JSONObject().put("ticket", token).put("nonce", b64(nonce))
                .put("data", b64(crypt(secret, nonce, payload.toString().toByteArray(), "jarvis-enroll-request-v1", true)))
            pending = JSONObject().put("ticket", token).put("id", id).put("alias", alias).put("request", sealed)
            store.put("direct_pending", pending.toString())
        }
        val client = OkHttpClient.Builder().connectTimeout(6, TimeUnit.SECONDS).readTimeout(10, TimeUnit.SECONDS).followRedirects(false).build()
        val response = client.newCall(Request.Builder().url(enroll.toString()).post(pending.getJSONObject("request").toString().toRequestBody("application/json".toMediaType())).build()).execute().use {
            val body = it.body?.string() ?: "{}"
            check(it.isSuccessful) {
                when (runCatching { JSONObject(body).optString("code") }.getOrDefault("")) {
                    "invitation_expired" -> "Convite expirado ou perdido após reiniciar o PC. Gere e escaneie um novo QR, sem reiniciar o Jarvis depois."
                    "invitation_used" -> "Este convite já foi usado por outro pedido. Gere um novo QR no PC."
                    "local_network_required" -> "O PC exige a rede local para parear. Conecte o celular ao mesmo Wi-Fi e confira a VPN."
                    else -> "PC recusou o pareamento (HTTP ${it.code}). Gere um novo QR no Jarvis atualizado."
                }
            }
            JSONObject(body)
        }
        val reply = JSONObject(String(crypt(secret, un64(response.getString("nonce")), un64(response.getString("data")), "jarvis-enroll-response-v1", false)))
        require(reply.getString("id") == pending.getString("id") && reply.getString("url") == direct)
        val cert = certificate(reply.getString("cert")); cert.verify(root.publicKey); cert.checkValidity()
        require(MessageDigest.isEqual(cert.publicKey.encoded, keyStore().getCertificate(pending.getString("alias")).publicKey.encoded))
        store.put("direct_config", JSONObject().put("id", reply.getString("id")).put("alias", pending.getString("alias"))
            .put("cert", reply.getString("cert")).put("ca", ticket.getString("ca")).put("url", direct)
            .put("local_url", URI("https", null, enroll.host, URI(direct).port.takeIf { it > 0 } ?: 9443, null, null, null).toString())
            .put("external_url", direct).toString())
        store.put("direct_pending", "{}"); store.put("direct_enabled", "true")
    }
    fun sync(context: Context, body: JSONObject): JSONObject {
        val cfg = JSONObject(SecureStore(context).get("direct_config"))
        val root = certificate(cfg.getString("ca")); val cert = certificate(cfg.getString("cert"))
        val trust = KeyStore.getInstance(KeyStore.getDefaultType()).apply { load(null); setCertificateEntry("jarvis", root) }
        val manager = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm()).apply { init(trust) }.trustManagers.filterIsInstance<X509TrustManager>().single()
        val alias = cfg.getString("alias")
        val keys = object : X509KeyManager {
            override fun getClientAliases(keyType: String?, issuers: Array<out Principal>?) = arrayOf(alias)
            override fun chooseClientAlias(types: Array<out String>?, issuers: Array<out Principal>?, socket: Socket?) = if (types?.any { it == "EC" } == true) alias else null
            override fun getServerAliases(type: String?, issuers: Array<out Principal>?) = null
            override fun chooseServerAlias(type: String?, issuers: Array<out Principal>?, socket: Socket?) = null
            override fun getCertificateChain(name: String?) = arrayOf(cert, root)
            override fun getPrivateKey(name: String?) = keyStore().getKey(alias, null) as PrivateKey
        }
        val tls = SSLContext.getInstance("TLS").apply { init(arrayOf(keys), arrayOf(manager), SecureRandom()) }
        val client = OkHttpClient.Builder().sslSocketFactory(tls.socketFactory, manager).connectTimeout(6, TimeUnit.SECONDS).readTimeout(15, TimeUnit.SECONDS)
            .followRedirects(false).followSslRedirects(false).retryOnConnectionFailure(false).build()
        body.getJSONObject("device").put("id", cfg.getString("id"))
        val data = body.toString().toByteArray()
        val urls = listOf(cfg.optString("local_url", cfg.getString("url")), cfg.optString("external_url"))
            .filter { it.isNotBlank() }.map { ServerAddress.normalize(it).also { value -> require(value.startsWith("https://")) } }.distinct()
        var lastError: java.io.IOException? = null
        for ((index, url) in urls.withIndex()) {
            // Fresh signed nonce for each destination: a lost response must not replay a signed request.
            val stamp = (System.currentTimeMillis() / 1000).toString()
            val nonce = hex(ByteArray(16).also { SecureRandom().nextBytes(it) }); val path = "/api/continuity/sync"
            val canonical = "${cfg.getString("id")}\nPOST\n$path\n$stamp\n$nonce\n${hex(digest(data))}"
            val request = Request.Builder().url(url + path).post(data.toRequestBody("application/json".toMediaType()))
                .header("x-jarvis-device", cfg.getString("id")).header("x-jarvis-time", stamp).header("x-jarvis-nonce", nonce)
                .header("x-jarvis-signature", b64(sign(alias, canonical.toByteArray()))).build()
            try {
                val transport = if (urls.size > 1 && index == 0) client.newBuilder().connectTimeout(2, TimeUnit.SECONDS).build() else client
                return transport.newCall(request).execute().use {
                    check(it.isSuccessful) { "Canal direto recusado ou indisponível (HTTP ${it.code})." }
                    JSONObject(it.body?.string() ?: "{}")
                }
            } catch (error: javax.net.ssl.SSLException) {
                throw error // Certificate errors require correction; never bypass TLS verification.
            } catch (error: java.io.IOException) {
                lastError = error
            }
        }
        throw java.io.IOException(if (urls.size == 1) "PC inacessível. Fora do Wi-Fi, configure o endereço externo HTTPS no Canal direto protegido. ${lastError?.message}" else "PC inacessível pelos endereços local e externo. Confira a porta 9443 no roteador/firewall e se o PC está ligado. ${lastError?.message}", lastError)
    }
}
