package com.test.fridahook.ui;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.fragment.app.Fragment;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.test.fridahook.R;
import com.test.fridahook.adapter.LogAdapter;
import com.test.fridahook.native_lib.NativeCrypto;

import java.util.ArrayList;
import java.util.List;

public class NativeFragment extends Fragment {

    private EditText etEncryptInput;
    private Button btnEncrypt;
    private Button btnDecrypt;
    private TextView tvEncryptResult;
    private EditText etSignData;
    private EditText etSignSignature;
    private Button btnVerify;
    private TextView tvVerifyResult;
    private RecyclerView rvLogs;
    private LogAdapter logAdapter;
    private List<LogAdapter.LogItem> logItems = new ArrayList<>();
    private String lastEncrypted;

    @Nullable
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, @Nullable ViewGroup container, @Nullable Bundle savedInstanceState) {
        return inflater.inflate(R.layout.fragment_native, container, false);
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle savedInstanceState) {
        super.onViewCreated(view, savedInstanceState);

        etEncryptInput = view.findViewById(R.id.et_encrypt_input);
        btnEncrypt = view.findViewById(R.id.btn_encrypt);
        btnDecrypt = view.findViewById(R.id.btn_decrypt);
        tvEncryptResult = view.findViewById(R.id.tv_encrypt_result);
        etSignData = view.findViewById(R.id.et_sign_data);
        etSignSignature = view.findViewById(R.id.et_sign_signature);
        btnVerify = view.findViewById(R.id.btn_verify);
        tvVerifyResult = view.findViewById(R.id.tv_verify_result);
        rvLogs = view.findViewById(R.id.rv_native_logs);

        setupRecyclerView();
        setupButtons();
    }

    private void setupRecyclerView() {
        logAdapter = new LogAdapter(logItems);
        rvLogs.setLayoutManager(new LinearLayoutManager(requireContext()));
        rvLogs.setAdapter(logAdapter);
    }

    private void setupButtons() {
        btnEncrypt.setOnClickListener(v -> {
            String input = etEncryptInput.getText().toString().trim();
            if (input.isEmpty()) return;
            String encrypted = NativeCrypto.encrypt(input);
            lastEncrypted = encrypted;
            tvEncryptResult.setText(encrypted);
            addLog("encrypt(\"" + input + "\") → " + encrypted, LogAdapter.TYPE_REQUEST);
        });

        btnDecrypt.setOnClickListener(v -> {
            String encrypted = lastEncrypted;
            if (encrypted == null || encrypted.isEmpty()) {
                encrypted = etEncryptInput.getText().toString().trim();
            }
            if (encrypted.isEmpty()) return;
            String decrypted = NativeCrypto.decrypt(encrypted);
            tvEncryptResult.setText(decrypted);
            addLog("decrypt(\"" + encrypted + "\") → " + decrypted, LogAdapter.TYPE_RESPONSE);
        });

        btnVerify.setOnClickListener(v -> {
            String data = etSignData.getText().toString().trim();
            String signature = etSignSignature.getText().toString().trim();
            if (data.isEmpty()) return;
            boolean valid = NativeCrypto.verifySignature(data, signature);
            tvVerifyResult.setText(valid ? "✓ Valid" : "✗ Invalid");
            addLog("verifySignature(\"" + data + "\", \"" + signature + "\") → " + valid,
                    valid ? LogAdapter.TYPE_RESPONSE : LogAdapter.TYPE_ERROR);
        });
    }

    private void addLog(String message, int type) {
        logItems.add(new LogAdapter.LogItem(message, type));
        logAdapter.notifyItemInserted(logItems.size() - 1);
        rvLogs.smoothScrollToPosition(logItems.size() - 1);
    }
}
