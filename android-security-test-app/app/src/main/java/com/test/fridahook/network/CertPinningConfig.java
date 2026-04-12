package com.test.fridahook.network;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.CertificatePinner;
import okhttp3.Interceptor;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

public class CertPinningConfig {

    public static CertificatePinner createPinner() {
        return new CertificatePinner.Builder()
                .add("httpbin.org", "sha256/...............")
                .build();
    }

    public static OkHttpClient.Builder applyPinning(OkHttpClient.Builder builder, boolean enabled) {
        if (enabled) {
            builder.certificatePinner(createPinner());
        }
        return builder;
    }
}
