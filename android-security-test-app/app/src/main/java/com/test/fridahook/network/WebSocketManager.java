package com.test.fridahook.network;

import android.util.Log;

import java.util.concurrent.TimeUnit;

import com.test.fridahook.App;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;

public class WebSocketManager {

    private static final String TAG = "WebSocketManager";

    public interface Listener {
        void onOpen();
        void onMessage(String text);
        void onClose(int code, String reason);
        void onError(String error);
    }

    private final Listener listener;
    private WebSocket webSocket;
    private OkHttpClient client;

    public WebSocketManager(Listener listener) {
        this.listener = listener;
    }

    public void connect(String url) {
        if (webSocket != null) {
            disconnect(1000, "Reconnecting");
        }

        client = App.get().getOkHttpClient().newBuilder()
                .readTimeout(0, TimeUnit.MILLISECONDS)
                .pingInterval(30, TimeUnit.SECONDS)
                .addInterceptor(new AppInterceptor())
                .build();

        Request request = new Request.Builder().url(url).build();
        webSocket = client.newWebSocket(request, new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                Log.d(TAG, "WebSocket opened: " + response.code());
                listener.onOpen();
            }

            @Override
            public void onMessage(WebSocket webSocket, String text) {
                Log.d(TAG, "WebSocket message: " + text);
                listener.onMessage(text);
            }

            @Override
            public void onClosing(WebSocket webSocket, int code, String reason) {
                Log.d(TAG, "WebSocket closing: " + code + " " + reason);
                webSocket.close(code, reason);
            }

            @Override
            public void onClosed(WebSocket webSocket, int code, String reason) {
                Log.d(TAG, "WebSocket closed: " + code + " " + reason);
                listener.onClose(code, reason);
            }

            @Override
            public void onFailure(WebSocket webSocket, Throwable t, Response response) {
                Log.e(TAG, "WebSocket failure", t);
                listener.onError(t.getMessage());
            }
        });
    }

    public void send(String text) {
        if (webSocket != null) {
            webSocket.send(text);
            Log.d(TAG, "WebSocket sent: " + text);
        }
    }

    public void disconnect(int code, String reason) {
        if (webSocket != null) {
            webSocket.close(code, reason);
            webSocket = null;
        }
    }
}
