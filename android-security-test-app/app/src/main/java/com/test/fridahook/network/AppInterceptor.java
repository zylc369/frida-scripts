package com.test.fridahook.network;

import android.util.Log;

import java.io.IOException;

import okhttp3.Interceptor;
import okhttp3.Request;
import okhttp3.Response;

public class AppInterceptor implements Interceptor {

    private static final String TAG = "AppInterceptor";

    @Override
    public Response intercept(Chain chain) throws IOException {
        Request original = chain.request();
        Request.Builder builder = original.newBuilder();

        builder.addHeader("X-App-Version", "1.0.0");
        builder.addHeader("X-Request-Id", String.valueOf(System.currentTimeMillis()));

        Request request = builder.build();

        Log.d(TAG, "App Interceptor: " + request.method() + " " + request.url());
        Log.d(TAG, "  Headers: " + request.headers());

        Response response = chain.proceed(request);

        Log.d(TAG, "  Response: " + response.code());
        return response;
    }
}
