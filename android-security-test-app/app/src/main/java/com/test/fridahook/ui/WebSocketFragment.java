package com.test.fridahook.ui;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.fragment.app.Fragment;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.test.fridahook.R;
import com.test.fridahook.adapter.LogAdapter;
import com.test.fridahook.network.WebSocketManager;

import java.util.ArrayList;
import java.util.List;

public class WebSocketFragment extends Fragment {

    private EditText etWsUrl;
    private Button btnConnect;
    private Button btnDisconnect;
    private EditText etMessage;
    private Button btnSend;
    private RecyclerView rvLogs;
    private LogAdapter logAdapter;
    private List<LogAdapter.LogItem> logItems = new ArrayList<>();
    private WebSocketManager webSocketManager;

    @Nullable
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, @Nullable ViewGroup container, @Nullable Bundle savedInstanceState) {
        return inflater.inflate(R.layout.fragment_websocket, container, false);
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle savedInstanceState) {
        super.onViewCreated(view, savedInstanceState);

        etWsUrl = view.findViewById(R.id.et_ws_url);
        btnConnect = view.findViewById(R.id.btn_connect);
        btnDisconnect = view.findViewById(R.id.btn_disconnect);
        etMessage = view.findViewById(R.id.et_ws_message);
        btnSend = view.findViewById(R.id.btn_send);
        rvLogs = view.findViewById(R.id.rv_ws_logs);

        setupRecyclerView();
        setupButtons();

        etWsUrl.setText("wss://echo.websocket.org");
    }

    private void setupRecyclerView() {
        logAdapter = new LogAdapter(logItems);
        rvLogs.setLayoutManager(new LinearLayoutManager(requireContext()));
        rvLogs.setAdapter(logAdapter);
    }

    private void setupButtons() {
        webSocketManager = new WebSocketManager(new WebSocketManager.Listener() {
            @Override
            public void onOpen() {
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() -> {
                        addLog(getString(R.string.log_connected), LogAdapter.TYPE_RESPONSE);
                        btnConnect.setEnabled(false);
                        btnDisconnect.setEnabled(true);
                    });
                }
            }

            @Override
            public void onMessage(String text) {
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() -> {
                        addLog(getString(R.string.log_rx) + " " + text, LogAdapter.TYPE_RESPONSE);
                    });
                }
            }

            @Override
            public void onClose(int code, String reason) {
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() -> {
                        addLog(getString(R.string.log_closed) + " code=" + code + " reason=" + reason, LogAdapter.TYPE_ERROR);
                        btnConnect.setEnabled(true);
                        btnDisconnect.setEnabled(false);
                    });
                }
            }

            @Override
            public void onError(String error) {
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() -> {
                        addLog(getString(R.string.log_error_prefix) + " " + error, LogAdapter.TYPE_ERROR);
                    });
                }
            }
        });

        btnConnect.setOnClickListener(v -> {
            String url = etWsUrl.getText().toString().trim();
            if (url.isEmpty()) return;
            addLog(getString(R.string.log_connecting) + " " + url, LogAdapter.TYPE_REQUEST);
            webSocketManager.connect(url);
        });

        btnDisconnect.setOnClickListener(v -> {
            webSocketManager.disconnect(1000, "User disconnect");
        });

        btnSend.setOnClickListener(v -> {
            String msg = etMessage.getText().toString().trim();
            if (msg.isEmpty()) return;
            webSocketManager.send(msg);
            addLog(getString(R.string.log_tx) + " " + msg, LogAdapter.TYPE_REQUEST);
            etMessage.setText("");
        });
    }

    private void addLog(String message, int type) {
        logItems.add(new LogAdapter.LogItem(message, type));
        logAdapter.notifyItemInserted(logItems.size() - 1);
        rvLogs.smoothScrollToPosition(logItems.size() - 1);
    }

    @Override
    public void onDestroyView() {
        super.onDestroyView();
        if (webSocketManager != null) {
            webSocketManager.disconnect(1000, "Fragment destroyed");
        }
    }
}
