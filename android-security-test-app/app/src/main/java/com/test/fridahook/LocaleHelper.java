package com.test.fridahook;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.os.LocaleList;

import java.util.Locale;

public class LocaleHelper {

    private static final String PREFS_NAME = "app_settings";
    private static final String KEY_LANGUAGE = "language";
    public static final String LANG_FOLLOW_SYSTEM = "system";
    public static final String LANG_CHINESE = "zh";
    public static final String LANG_ENGLISH = "en";

    public static Context applyLocale(Context context) {
        String savedLang = getSavedLanguage(context);
        Locale locale;

        if (LANG_FOLLOW_SYSTEM.equals(savedLang)) {
            locale = Locale.getDefault();
        } else {
            locale = new Locale(savedLang);
        }

        Locale.setDefault(locale);

        Configuration config = new Configuration();
        config.setLocale(locale);
        LocaleList localeList = new LocaleList(locale);
        LocaleList.setDefault(localeList);
        config.setLocales(localeList);

        return context.createConfigurationContext(config);
    }

    public static void saveLanguage(Context context, String language) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit().putString(KEY_LANGUAGE, language).apply();
    }

    public static String getSavedLanguage(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        return prefs.getString(KEY_LANGUAGE, LANG_FOLLOW_SYSTEM);
    }
}
