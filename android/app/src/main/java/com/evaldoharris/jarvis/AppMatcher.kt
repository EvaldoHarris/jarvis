package com.evaldoharris.jarvis

import java.text.Normalizer

/** Encontra o aplicativo pelo nome falado, tolerando acentos, espaços e pequenas diferenças. */
internal object AppMatcher {
    private fun norm(text: String) = Normalizer.normalize(text, Normalizer.Form.NFD).replace(Regex("\\p{M}"), "")
        .lowercase(java.util.Locale.ROOT).replace(Regex("[^a-z0-9]"), "")
    /** Palavras de ligação que a voz costuma trazer junto do nome ("o app do WhatsApp"). */
    private fun clean(text: String) = text.lowercase(java.util.Locale.ROOT)
        .replace(Regex("\\b(o|a|os|as|app|aplicativo|do|da|de|no|na)\\b"), " ").trim()

    private fun distance(a: String, b: String): Int {
        val row = IntArray(b.length + 1) { it }
        for (i in 1..a.length) {
            var previous = row[0]; row[0] = i
            for (j in 1..b.length) {
                val saved = row[j]
                row[j] = minOf(row[j] + 1, row[j - 1] + 1, previous + if (a[i - 1] == b[j - 1]) 0 else 1)
                previous = saved
            }
        }
        return row[b.length]
    }

    /** Pontuação: maior é melhor; 0 significa sem relação. */
    private fun score(query: String, label: String, pkg: String): Int {
        val q = norm(clean(query)).ifEmpty { norm(query) }
        val l = norm(label)
        if (q.isEmpty() || l.isEmpty()) return 0
        return when {
            q == l || query == pkg -> 1000
            l.startsWith(q) -> 800 - (l.length - q.length)
            q.startsWith(l) && l.length >= 4 -> 700 - (q.length - l.length)
            l.contains(q) && q.length >= 3 -> 600 - (l.length - q.length)
            norm(pkg).contains(q) && q.length >= 4 -> 500
            q.length >= 4 && distance(q, l) <= maxOf(1, q.length / 4) -> 400 - distance(q, l) * 10
            else -> 0
        }
    }

    /** Devolve (nome, pacote) do melhor app, ou null se nenhum servir ou houver empate real. */
    fun best(query: String, apps: List<Pair<String, String>>): Pair<String, String>? {
        val ranked = apps.map { it to score(query, it.first, it.second) }.filter { it.second > 0 }.sortedByDescending { it.second }
        val top = ranked.firstOrNull() ?: return null
        val second = ranked.getOrNull(1)
        // Empate exato entre nomes diferentes: melhor pedir confirmação do que abrir o errado.
        if (second != null && second.second == top.second && top.second < 1000) return null
        return top.first
    }

    fun suggestions(query: String, labels: List<String>): List<String> {
        val q = norm(clean(query))
        return labels.sortedBy { distance(q, norm(it)) }.take(5)
    }
}
