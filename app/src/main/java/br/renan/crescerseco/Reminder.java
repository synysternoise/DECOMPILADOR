package br.renan.crescerseco;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;

import java.util.Calendar;

/** Lembretes diários de sono: um para desligar as telas e outro para deitar. */
public class Reminder extends BroadcastReceiver {
    static final String PREFS = "sono";
    private static final String CHANNEL = "sono";
    private static final int WIND = 1;
    private static final int BED = 2;

    @Override
    public void onReceive(Context ctx, Intent intent) {
        int kind = intent.getIntExtra("kind", 0);
        if (kind == WIND) {
            show(ctx, WIND, "Hora de desligar", "Telas fora, magnésio e luz baixa. Cama daqui a pouco.");
        } else if (kind == BED) {
            show(ctx, BED, "Hora de dormir", "Deite agora para fechar quase 7 horas até as 03:10.");
        }
        // Depois de tocar (ou depois de o celular reiniciar), agenda o próximo.
        schedule(ctx);
    }

    static void schedule(Context ctx) {
        SharedPreferences sp = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        boolean on = sp.getBoolean("on", false);
        set(ctx, WIND, on, sp.getString("wind", "19:30"));
        set(ctx, BED, on, sp.getString("bed", "20:15"));
    }

    private static void set(Context ctx, int kind, boolean on, String time) {
        AlarmManager am = (AlarmManager) ctx.getSystemService(Context.ALARM_SERVICE);
        Intent intent = new Intent(ctx, Reminder.class).putExtra("kind", kind);
        PendingIntent pi = PendingIntent.getBroadcast(ctx, kind, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        am.cancel(pi);
        if (!on) {
            return;
        }
        int hour = 20;
        int minute = 15;
        try {
            String[] parts = time.split(":");
            hour = Integer.parseInt(parts[0]);
            minute = Integer.parseInt(parts[1]);
        } catch (Exception ignored) {
        }
        Calendar c = Calendar.getInstance();
        c.set(Calendar.HOUR_OF_DAY, hour);
        c.set(Calendar.MINUTE, minute);
        c.set(Calendar.SECOND, 0);
        c.set(Calendar.MILLISECOND, 0);
        if (c.getTimeInMillis() <= System.currentTimeMillis() + 60000) {
            c.add(Calendar.DAY_OF_YEAR, 1);
        }
        am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, c.getTimeInMillis(), pi);
    }

    private static void show(Context ctx, int id, String title, String text) {
        NotificationManager nm = (NotificationManager) ctx.getSystemService(Context.NOTIFICATION_SERVICE);
        nm.createNotificationChannel(new NotificationChannel(CHANNEL, "Lembretes de sono",
                NotificationManager.IMPORTANCE_HIGH));
        PendingIntent open = PendingIntent.getActivity(ctx, 0, new Intent(ctx, MainActivity.class),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification n = new Notification.Builder(ctx, CHANNEL)
                .setSmallIcon(R.drawable.ic_stat)
                .setContentTitle(title)
                .setContentText(text)
                .setContentIntent(open)
                .setAutoCancel(true)
                .build();
        try {
            nm.notify(id, n);
        } catch (SecurityException ignored) {
            // Sem permissão de notificação: o usuário não liberou.
        }
    }
}
