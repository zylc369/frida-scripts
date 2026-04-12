package com.test.fridahook.ui;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.Button;
import com.google.android.material.switchmaterial.SwitchMaterial;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.Spinner;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.fragment.app.Fragment;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.test.fridahook.R;
import com.test.fridahook.adapter.LogAdapter;
import com.test.fridahook.network.OkHttpHelper;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

public class NetworkFragment extends Fragment {

    private EditText etUrl;
    private Spinner spinnerMethod;
    private EditText etBody;
    private EditText etTimeout;
    private EditText etRetryCount;
    private SwitchMaterial cbCertPinning;
    private LinearLayout headerContainer;
    private Button btnAddHeader;
    private Button btnUpload;
    private Button btnDownload;
    private Button btnSend;
    private RecyclerView rvLogs;
    private LogAdapter logAdapter;
    private List<LogAdapter.LogItem> logItems = new ArrayList<>();

    @Nullable
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, @Nullable ViewGroup container, @Nullable Bundle savedInstanceState) {
        return inflater.inflate(R.layout.fragment_network, container, false);
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle savedInstanceState) {
        super.onViewCreated(view, savedInstanceState);

        etUrl = view.findViewById(R.id.et_url);
        spinnerMethod = view.findViewById(R.id.spinner_method);
        etBody = view.findViewById(R.id.et_body);
        etTimeout = view.findViewById(R.id.et_timeout);
        etRetryCount = view.findViewById(R.id.et_retry_count);
        cbCertPinning = view.findViewById(R.id.cb_cert_pinning);
        headerContainer = view.findViewById(R.id.header_container);
        btnAddHeader = view.findViewById(R.id.btn_add_header);
        btnUpload = view.findViewById(R.id.btn_upload);
        btnDownload = view.findViewById(R.id.btn_download);
        btnSend = view.findViewById(R.id.btn_send);
        rvLogs = view.findViewById(R.id.rv_logs);

        setupMethodSpinner();
        setupRecyclerView();
        setupButtons();

        etUrl.setText("https://httpbin.org");
        etTimeout.setText("30");
        etRetryCount.setText("3");
    }

    private void setupMethodSpinner() {
        String[] methods = {"GET", "POST", "PUT", "DELETE", "PATCH"};
        ArrayAdapter<String> adapter = new ArrayAdapter<>(requireContext(),
                android.R.layout.simple_spinner_item, methods);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        spinnerMethod.setAdapter(adapter);
    }

    private void setupRecyclerView() {
        logAdapter = new LogAdapter(logItems);
        rvLogs.setLayoutManager(new LinearLayoutManager(requireContext()));
        rvLogs.setAdapter(logAdapter);
    }

    private void setupButtons() {
        btnAddHeader.setOnClickListener(v -> addHeaderRow());

        btnSend.setOnClickListener(v -> sendRequest());

        btnUpload.setOnClickListener(v -> uploadFile());

        btnDownload.setOnClickListener(v -> downloadFile());
    }

    private void addHeaderRow() {
        LinearLayout row = new LinearLayout(requireContext());
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setLayoutParams(new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT));

        EditText etKey = new EditText(requireContext());
        etKey.setHint("Key");
        etKey.setLayoutParams(new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        etKey.setSingleLine(true);

        EditText etValue = new EditText(requireContext());
        etValue.setHint("Value");
        etValue.setLayoutParams(new LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        etValue.setSingleLine(true);

        Button btnRemove = new Button(requireContext());
        btnRemove.setText("✕");
        btnRemove.setLayoutParams(new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT));
        btnRemove.setOnClickListener(v2 -> headerContainer.removeView(row));

        row.addView(etKey);
        row.addView(etValue);
        row.addView(btnRemove);
        headerContainer.addView(row, headerContainer.getChildCount() - 1);
    }

    private OkHttpHelper.RequestConfig buildConfig() {
        OkHttpHelper.RequestConfig config = new OkHttpHelper.RequestConfig();
        config.url = etUrl.getText().toString().trim();
        config.method = spinnerMethod.getSelectedItem().toString();
        config.body = etBody.getText().toString().trim();
        config.timeoutSeconds = Integer.parseInt(etTimeout.getText().toString().trim());
        config.retryCount = Integer.parseInt(etRetryCount.getText().toString().trim());
        config.certPinningEnabled = cbCertPinning.isChecked();

        for (int i = 0; i < headerContainer.getChildCount(); i++) {
            View child = headerContainer.getChildAt(i);
            if (child instanceof LinearLayout) {
                LinearLayout row = (LinearLayout) child;
                if (row.getChildCount() >= 2) {
                    EditText etKey = (EditText) row.getChildAt(0);
                    EditText etVal = (EditText) row.getChildAt(1);
                    String key = etKey.getText().toString().trim();
                    String val = etVal.getText().toString().trim();
                    if (!key.isEmpty() && !val.isEmpty()) {
                        config.headers.put(key, val);
                    }
                }
            }
        }
        return config;
    }

    private void sendRequest() {
        OkHttpHelper.RequestConfig config = buildConfig();
        addLog("[Request] " + config.method + " " + config.url, LogAdapter.TYPE_REQUEST);

        OkHttpHelper.sendRequest(config, new OkHttpHelper.Callback() {
            @Override
            public void onResponse(String response) {
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() -> {
                        addLog("[Response]\n" + response, LogAdapter.TYPE_RESPONSE);
                    });
                }
            }

            @Override
            public void onError(String error) {
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() -> {
                        addLog("[Error] " + error, LogAdapter.TYPE_ERROR);
                    });
                }
            }
        });
    }

    private void uploadFile() {
        OkHttpHelper.RequestConfig config = buildConfig();
        if (config.url.isEmpty()) {
            config.url = "https://httpbin.org/post";
            etUrl.setText(config.url);
        }
        config.method = "POST";

        File testFile = OkHttpHelper.createTestUploadFile(requireContext());
        addLog("[Upload] " + config.url + " file=" + testFile.getName(), LogAdapter.TYPE_REQUEST);

        OkHttpHelper.uploadFile(config, testFile, new OkHttpHelper.Callback() {
            @Override
            public void onResponse(String response) {
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() -> {
                        addLog("[Upload Response]\n" + response, LogAdapter.TYPE_RESPONSE);
                    });
                }
            }

            @Override
            public void onError(String error) {
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() -> {
                        addLog("[Upload Error] " + error, LogAdapter.TYPE_ERROR);
                    });
                }
            }
        });
    }

    private void downloadFile() {
        OkHttpHelper.RequestConfig config = buildConfig();
        if (config.url.isEmpty()) {
            config.url = "https://httpbin.org/image/png";
            etUrl.setText(config.url);
        }

        addLog("[Download] " + config.url, LogAdapter.TYPE_REQUEST);

        OkHttpHelper.downloadFile(config, requireContext(), new OkHttpHelper.Callback() {
            @Override
            public void onResponse(String response) {
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() -> {
                        addLog("[Download Complete] " + response, LogAdapter.TYPE_RESPONSE);
                    });
                }
            }

            @Override
            public void onError(String error) {
                if (getActivity() != null) {
                    getActivity().runOnUiThread(() -> {
                        addLog("[Download Error] " + error, LogAdapter.TYPE_ERROR);
                    });
                }
            }
        });
    }

    private void addLog(String message, int type) {
        logItems.add(new LogAdapter.LogItem(message, type));
        logAdapter.notifyItemInserted(logItems.size() - 1);
        rvLogs.smoothScrollToPosition(logItems.size() - 1);
    }
}
