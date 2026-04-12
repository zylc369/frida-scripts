package com.test.fridahook;

import android.app.Application;
import android.content.Context;

import com.test.fridahook.network.CookieJarImpl;

import okhttp3.OkHttpClient;

public class App extends Application {

    private static App instance;
    private OkHttpClient okHttpClient;

    @Override
    public void onCreate() {
        super.onCreate();
        instance = this;
        initOkHttpClient();
    }

    @Override
    protected void attachBaseContext(Context base) {
        super.attachBaseContext(LocaleHelper.applyLocale(base));
    }

    private void initOkHttpClient() {
        okHttpClient = new OkHttpClient.Builder()
                .cookieJar(new CookieJarImpl(this))
                .followRedirects(true)
                .followSslRedirects(true)
                .build();
    }

    public static App get() {
        return instance;
    }

    public OkHttpClient getOkHttpClient() {
        return okHttpClient;
    }

    public static Context getContext() {
        return instance.getApplicationContext();
    }
}
