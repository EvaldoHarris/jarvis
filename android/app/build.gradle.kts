import java.net.URI
import java.security.MessageDigest

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}
android {
    namespace = "com.evaldoharris.jarvis"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.evaldoharris.jarvis"
        minSdk = 30
        targetSdk = 35
        versionCode = 31
        versionName = "0.9.6"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    sourceSets.getByName("main").assets.srcDir(layout.buildDirectory.dir("generated/translationVoiceAssets"))

}
dependencies {
    implementation("com.k2fsa:sherpa-onnx-static-link-onnxruntime:1.12.40@aar")
    implementation("com.google.mlkit:translate:17.0.3")
    implementation("com.google.zxing:core:3.5.3")
    implementation("com.journeyapps:zxing-android-embedded:4.3.0")
    implementation("com.google.ai.edge.litertlm:litertlm-android:0.18.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    // Detector offline da palavra Jarvis (modelo pequeno de português em assets/vosk-pt)
    implementation("com.alphacephei:vosk-android:0.3.75@aar")
    implementation("net.java.dev.jna:jna:5.19.1@aar")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.media3:media3-exoplayer:1.5.1")
    implementation("androidx.media3:media3-exoplayer-rtsp:1.5.1")
    implementation("androidx.media3:media3-ui:1.5.1")
    testImplementation("junit:junit:4.13.2")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
}

kotlin { compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) } }

// Pin and verify the public voice model; package it so narration needs no phone download.
val prepareTranslationVoice by tasks.registering {
    val expected = "dbc8b1d7d729fd417ea78a350ed35696c928770ac93513d3f507bd4e88eee3fd"
    val output = layout.buildDirectory.dir("generated/translationVoiceAssets/translation-voice")
    inputs.property("modelSha256", expected)
    outputs.dir(output)
    doLast {
        val archive = rootProject.file(".gradle/translation-voice.tar.bz2")
        if (!archive.isFile) {
            archive.parentFile.mkdirs()
            val connection = URI("https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-pt_BR-faber-medium-int8.tar.bz2").toURL().openConnection()
            connection.connectTimeout = 20000; connection.readTimeout = 40000
            connection.getInputStream().use { input -> archive.outputStream().use { input.copyTo(it) } }
        }
        val digest = MessageDigest.getInstance("SHA-256").digest(archive.readBytes()).joinToString("") { "%02x".format(it) }
        check(digest == expected) { "Voice checksum mismatch; remove android/.gradle/translation-voice.tar.bz2 and retry." }
        copy { from(tarTree(resources.bzip2(archive))); into(output) }
    }
}
tasks.named("preBuild") { dependsOn(prepareTranslationVoice) }
