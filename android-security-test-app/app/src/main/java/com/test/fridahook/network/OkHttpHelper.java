package com.test.fridahook.network;

import android.content.Context;
import android.util.Log;

import com.test.fridahook.App;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.Headers;
import okhttp3.MediaType;
import okhttp3.MultipartBody;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

public class OkHttpHelper {

    private static final String TAG = "OkHttpHelper";
    private static final MediaType JSON_TYPE = MediaType.get("application/json; charset=utf-8");
    private static final MediaType FILE_TYPE = MediaType.get("application/octet-stream");

    public static class RequestConfig {
        public String url = "";
        public String method = "GET";
        public String body = "";
        public int timeoutSeconds = 30;
        public int retryCount = 3;
        public boolean certPinningEnabled = false;
        public HashMap<String, String> headers = new HashMap<>();
    }

    public interface Callback {
        void onResponse(String response);
        void onError(String error);
    }

    public static void sendRequest(RequestConfig config, Callback callback) {
        try {
            OkHttpClient client = buildClient(config);

            RequestBody requestBody = null;
            if (!config.method.equals("GET") && !config.body.isEmpty()) {
                requestBody = RequestBody.create(config.body, JSON_TYPE);
            }

            Request.Builder requestBuilder = new Request.Builder()
                    .url(config.url);

            for (Map.Entry<String, String> header : config.headers.entrySet()) {
                requestBuilder.addHeader(header.getKey(), header.getValue());
            }

            switch (config.method) {
                case "GET":
                    requestBuilder.get();
                    break;
                case "POST":
                    requestBuilder.post(requestBody != null ? requestBody :
                            RequestBody.create("", JSON_TYPE));
                    break;
                case "PUT":
                    requestBuilder.put(requestBody != null ? requestBody :
                            RequestBody.create("", JSON_TYPE));
                    break;
                case "DELETE":
                    requestBuilder.delete(requestBody);
                    break;
                case "PATCH":
                    requestBuilder.patch(requestBody != null ? requestBody :
                            RequestBody.create("", JSON_TYPE));
                    break;
            }

            client.newCall(requestBuilder.build()).enqueue(new okhttp3.Callback() {
                @Override
                public void onFailure(Call call, IOException e) {
                    Log.e(TAG, "Request failed", e);
                    callback.onError(e.getMessage());
                }

                @Override
                public void onResponse(Call call, Response response) throws IOException {
                    String responseBody = response.body() != null ? response.body().string() : "";
                    StringBuilder sb = new StringBuilder();
                    sb.append("Status: ").append(response.code()).append("\n");
                    sb.append("Headers:\n");
                    for (String name : response.headers().names()) {
                        sb.append("  ").append(name).append(": ")
                                .append(response.headers().get(name)).append("\n");
                    }
                    sb.append("Body:\n").append(responseBody);
                    callback.onResponse(sb.toString());
                }
            });
        } catch (Exception e) {
            Log.e(TAG, "Error building request", e);
            callback.onError(e.getMessage());
        }
    }

    public static void uploadFile(RequestConfig config, File file, Callback callback) {
        try {
            OkHttpClient client = buildClient(config);

            MultipartBody.Builder multipartBuilder = new MultipartBody.Builder()
                    .setType(MultipartBody.FORM)
                    .addFormDataPart("file", file.getName(),
                            RequestBody.create(file, FILE_TYPE));

            if (!config.body.isEmpty()) {
                multipartBuilder.addFormDataPart("data", config.body);
            }

            for (Map.Entry<String, String> header : config.headers.entrySet()) {
                multipartBuilder.addFormDataPart(header.getKey(), header.getValue());
            }

            Request request = new Request.Builder()
                    .url(config.url)
                    .post(multipartBuilder.build())
                    .build();

            client.newCall(request).enqueue(new okhttp3.Callback() {
                @Override
                public void onFailure(Call call, IOException e) {
                    callback.onError(e.getMessage());
                }

                @Override
                public void onResponse(Call call, Response response) throws IOException {
                    String body = response.body() != null ? response.body().string() : "";
                    callback.onResponse("Status: " + response.code() + "\nBody: " + body);
                }
            });
        } catch (Exception e) {
            callback.onError(e.getMessage());
        }
    }

    public static void downloadFile(RequestConfig config, Context context, Callback callback) {
        try {
            OkHttpClient client = buildClient(config);

            Request request = new Request.Builder()
                    .url(config.url)
                    .build();

            client.newCall(request).enqueue(new okhttp3.Callback() {
                @Override
                public void onFailure(Call call, IOException e) {
                    callback.onError(e.getMessage());
                }

                @Override
                public void onResponse(Call call, Response response) throws IOException {
                    if (!response.isSuccessful()) {
                        callback.onError("HTTP " + response.code());
                        return;
                    }

                    File downloadsDir = context.getExternalFilesDir(android.os.Environment.DIRECTORY_DOWNLOADS);
                    if (downloadsDir == null) {
                        downloadsDir = context.getFilesDir();
                    }

                    String fileName = "download_" + System.currentTimeMillis();
                    String contentDisposition = response.header("Content-Disposition");
                    if (contentDisposition != null && contentDisposition.contains("filename=")) {
                        fileName = contentDisposition.split("filename=")[1].replace("\"", "").trim();
                    }

                    File outFile = new File(downloadsDir, fileName);
                    try (FileOutputStream fos = new FileOutputStream(outFile)) {
                        byte[] buffer = new byte[4096];
                        java.io.InputStream is = response.body().byteStream();
                        int read;
                        while ((read = is.read(buffer)) != -1) {
                            fos.write(buffer, 0, read);
                        }
                    }

                    callback.onResponse("Saved to: " + outFile.getAbsolutePath()
                            + " (" + outFile.length() + " bytes)");
                }
            });
        } catch (Exception e) {
            callback.onError(e.getMessage());
        }
    }

    public static File createTestUploadFile(Context context) {
        File file = new File(context.getCacheDir(), "test_upload_" + System.currentTimeMillis() + ".txt");
        try (FileOutputStream fos = new FileOutputStream(file)) {
            fos.write("This is a test file for OkHttp3 upload hook testing.\n".getBytes());
            fos.write(("Timestamp: " + System.currentTimeMillis() + "\n").getBytes());
            fos.write("Content for Frida hook verification.\n".getBytes());
        } catch (IOException e) {
            Log.e(TAG, "Failed to create test file", e);
        }
        return file;
    }

    private static OkHttpClient buildClient(RequestConfig config) {
        OkHttpClient.Builder builder = App.get().getOkHttpClient().newBuilder()
                .connectTimeout(config.timeoutSeconds, TimeUnit.SECONDS)
                .readTimeout(config.timeoutSeconds, TimeUnit.SECONDS)
                .writeTimeout(config.timeoutSeconds, TimeUnit.SECONDS)
                .addInterceptor(new AppInterceptor())
                .addNetworkInterceptor(new NetworkInterceptor())
                .addInterceptor(new RetryInterceptor(config.retryCount));

        CertPinningConfig.applyPinning(builder, config.certPinningEnabled);

        return builder.build();
    }
}
