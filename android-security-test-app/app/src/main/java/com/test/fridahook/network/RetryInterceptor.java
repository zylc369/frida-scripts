package com.test.fridahook.network;

import android.util.Log;

import java.io.IOException;

import okhttp3.Interceptor;
import okhttp3.Request;
import okhttp3.Response;

public class RetryInterceptor implements Interceptor {

    private static final String TAG = "RetryInterceptor";
    private final int maxRetry;
    private int retryCount = 0;

    public RetryInterceptor(int maxRetry) {
        this.maxRetry = maxRetry;
    }

    @Override
    public Response intercept(Chain chain) throws IOException {
        Request request = chain.request();
        Response response = null;
        IOException exception = null;

        while (retryCount < maxRetry) {
            try {
                response = chain.proceed(request);
                if (response.isSuccessful()) {
                    return response;
                }
            } catch (IOException e) {
                exception = e;
                Log.w(TAG, "Retry " + (retryCount + 1) + "/" + maxRetry + ": " + e.getMessage());
            }
            retryCount++;
        }

        if (exception != null) {
            throw exception;
        }
        if (response != null) {
            return response;
        }
        throw new IOException("Max retries exceeded");
    }
}
