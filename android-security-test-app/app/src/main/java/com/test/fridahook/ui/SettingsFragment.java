package com.test.fridahook.ui;

import android.content.Intent;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.RadioGroup;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.fragment.app.Fragment;

import com.test.fridahook.LocaleHelper;
import com.test.fridahook.MainActivity;
import com.test.fridahook.R;

public class SettingsFragment extends Fragment {

    @Nullable
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, @Nullable ViewGroup container, @Nullable Bundle savedInstanceState) {
        return inflater.inflate(R.layout.fragment_settings, container, false);
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle savedInstanceState) {
        super.onViewCreated(view, savedInstanceState);

        RadioGroup rgLanguage = view.findViewById(R.id.rg_language);
        TextView tvAbout = view.findViewById(R.id.tv_about);

        String savedLang = LocaleHelper.getSavedLanguage(requireContext());

        switch (savedLang) {
            case LocaleHelper.LANG_CHINESE:
                rgLanguage.check(R.id.rb_chinese);
                break;
            case LocaleHelper.LANG_ENGLISH:
                rgLanguage.check(R.id.rb_english);
                break;
            default:
                rgLanguage.check(R.id.rb_follow_system);
                break;
        }

        rgLanguage.setOnCheckedChangeListener((group, checkedId) -> {
            String lang;
            if (checkedId == R.id.rb_chinese) {
                lang = LocaleHelper.LANG_CHINESE;
            } else if (checkedId == R.id.rb_english) {
                lang = LocaleHelper.LANG_ENGLISH;
            } else {
                lang = LocaleHelper.LANG_FOLLOW_SYSTEM;
            }
            LocaleHelper.saveLanguage(requireContext(), lang);
            restartApp();
        });

        tvAbout.setText(getString(R.string.about_version) + "\n\n" + getString(R.string.about_description));
    }

    private void restartApp() {
        Intent intent = new Intent(requireContext(), MainActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
        startActivity(intent);
        Runtime.getRuntime().exit(0);
    }
}
