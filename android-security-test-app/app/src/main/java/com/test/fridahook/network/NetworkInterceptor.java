package com.test.fridahook.network;

import android.util.Log;

import java.io.IOException;

import okhttp3.Interceptor;
import okhttp3.Request;
import okhttp3.Response;

public class NetworkInterceptor implements Interceptor {

    private static final String TAG = "NetworkInterceptor";

    @Override
    public Response intercept(Chain chain) throws IOException {
        Request request = chain.request();
        long startNs = System.nanoTime();

        Log.d(TAG, "Network Interceptor: " + request.method() + " " + request.url());

        Response response;
        try {
            response = chain.proceed(request);
        } catch (IOException e) {
            Log.e(TAG, "Network failed: " + e.getMessage());
            throw e;
        }

        long tookMs = (System.nanoTime() - startNs) / 1_000_000;
        Log.d(TAG, "  " + response.code() + " " + response.request().url()
                + " (" + tookMs + "ms)");

        if (response.priorResponse() != null) {
            Log.d(TAG, "  Redirect: " + response.priorResponse().code()
                    + " → " + response.request().url());
        }

        return response;
    }
}
