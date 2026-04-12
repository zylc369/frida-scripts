package com.test.fridahook.network;

import android.content.Context;
import android.content.SharedPreferences;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import okhttp3.Cookie;
import okhttp3.CookieJar;
import okhttp3.HttpUrl;

public class CookieJarImpl implements CookieJar {

    private static final String PREFS_NAME = "okhttp_cookies";
    private final SharedPreferences prefs;

    public CookieJarImpl(Context context) {
        prefs = context.getApplicationContext().getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    }

    @Override
    public void saveFromResponse(HttpUrl url, List<Cookie> cookies) {
        SharedPreferences.Editor editor = prefs.edit();
        for (Cookie cookie : cookies) {
            editor.putString(cookieKey(url, cookie.name()), cookie.toString());
        }
        editor.apply();
    }

    @Override
    public List<Cookie> loadForRequest(HttpUrl url) {
        List<Cookie> cookies = new ArrayList<>();
        Map<String, ?> all = prefs.getAll();
        for (Map.Entry<String, ?> entry : all.entrySet()) {
            String[] parts = ((String) entry.getValue()).split(";");
            for (String part : parts) {
                String[] kv = part.trim().split("=", 2);
                if (kv.length == 2) {
                    Cookie cookie = new Cookie.Builder()
                            .name(kv[0].trim())
                            .value(kv[1].trim())
                            .domain(url.host())
                            .build();
                    cookies.add(cookie);
                }
            }
        }
        return cookies;
    }

    private String cookieKey(HttpUrl url, String name) {
        return url.host() + "|" + name;
    }

    public void clear() {
        prefs.edit().clear().apply();
    }
}
