package com.evaldoharris.jarvis

import android.app.AlarmManager
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.net.Uri
import org.json.JSONObject

object TaskReminders {
    fun enabled(context: Context) = context.getSystemService(NotificationManager::class.java).areNotificationsEnabled()
    private fun alarm(context: Context, id: String): PendingIntent = PendingIntent.getBroadcast(context, 0,
        Intent(context, TaskReminderReceiver::class.java).setAction("remind").setData(Uri.parse("jarvis://task/$id")).putExtra("id", id),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    fun schedule(context: Context, task: JSONObject) {
        val due = task.optLong("due_ms")
        if (due > 0 && !task.optBoolean("done") && !task.optBoolean("notified")) {
            context.getSystemService(AlarmManager::class.java).setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,
                maxOf(due, System.currentTimeMillis() + 1000), alarm(context, task.getString("id")))
        }
    }
    fun cancel(context: Context, id: String) {
        context.getSystemService(AlarmManager::class.java).cancel(alarm(context, id))
        context.getSystemService(NotificationManager::class.java).cancel(id, 3)
    }
    fun restore(context: Context) {
        val entries = PersonalData.read(context, "tasks")
        for (i in 0 until entries.length()) schedule(context, entries.getJSONObject(i))
    }
}

class TaskReminderReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action in listOf(Intent.ACTION_BOOT_COMPLETED, Intent.ACTION_MY_PACKAGE_REPLACED)) { TaskReminders.restore(context); return }
        val id = intent.getStringExtra("id") ?: return
        synchronized(PersonalData) {
            val entries = PersonalData.read(context, "tasks")
            val task = (0 until entries.length()).map { entries.getJSONObject(it) }.firstOrNull { it.getString("id") == id } ?: return
            if (task.optBoolean("done") || task.optBoolean("notified") || task.optLong("due_ms") > System.currentTimeMillis()) return
            if (!TaskReminders.enabled(context)) return
            val manager = context.getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(NotificationChannel("jarvis_tasks", "Tarefas do JARVIS", NotificationManager.IMPORTANCE_DEFAULT))
            val open = PendingIntent.getActivity(context, 0, Intent(context, PersonalActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
            try {
                manager.notify(id, 3, Notification.Builder(context, "jarvis_tasks").setSmallIcon(R.drawable.ic_reactor)
                    .setContentTitle("JARVIS — lembrete").setContentText(task.getString("title"))
                    .setStyle(Notification.BigTextStyle().bigText(task.getString("title"))).setContentIntent(open).setAutoCancel(true).build())
                task.put("notified", true); PersonalData.write(context, "tasks", entries)
            } catch (_: SecurityException) { }
        }
    }
}
