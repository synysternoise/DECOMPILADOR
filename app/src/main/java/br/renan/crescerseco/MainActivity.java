package br.renan.crescerseco;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

/** Abre o plano (assets/index.html) em tela cheia. Os dados ficam no armazenamento do próprio app. */
public class MainActivity extends Activity {
    private static final int NIGHT = 0xFF0B0D13;
    private WebView web;

    /** Ponte chamada pela página (window.Android) para ligar e desligar os lembretes de sono. */
    private class Bridge {
        @JavascriptInterface
        public void setReminders(final boolean on, final String wind, final String bed) {
            getSharedPreferences(Reminder.PREFS, Context.MODE_PRIVATE).edit()
                    .putBoolean("on", on)
                    .putString("wind", wind)
                    .putString("bed", bed)
                    .apply();
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    if (on && Build.VERSION.SDK_INT >= 33
                            && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                            != PackageManager.PERMISSION_GRANTED) {
                        requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1);
                    }
                    Reminder.schedule(MainActivity.this);
                }
            });
        }
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // Tela ligada durante o treino, para o timer de descanso ficar visível.
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getWindow().setStatusBarColor(NIGHT);
        getWindow().setNavigationBarColor(NIGHT);

        web = new WebView(this);
        web.setBackgroundColor(NIGHT);
        WebSettings st = web.getSettings();
        st.setJavaScriptEnabled(true);
        st.setDomStorageEnabled(true);
        st.setMediaPlaybackRequiresUserGesture(false);
        web.addJavascriptInterface(new Bridge(), "Android");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if ("file".equals(uri.getScheme())) {
                    return false;
                }
                // Links de vídeo abrem no YouTube ou no navegador.
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, uri));
                } catch (Exception ignored) {
                }
                return true;
            }
        });
        setContentView(web);
        web.loadUrl("file:///android_asset/index.html");
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
