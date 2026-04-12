package com.test.fridahook.adapter;

import android.graphics.Color;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.test.fridahook.R;

import java.util.List;

public class LogAdapter extends RecyclerView.Adapter<LogAdapter.ViewHolder> {

    public static final int TYPE_REQUEST = 0;
    public static final int TYPE_RESPONSE = 1;
    public static final int TYPE_ERROR = 2;

    private final List<LogItem> items;

    public static class LogItem {
        public final String message;
        public final int type;
        public final long timestamp;

        public LogItem(String message, int type) {
            this.message = message;
            this.type = type;
            this.timestamp = System.currentTimeMillis();
        }
    }

    public LogAdapter(List<LogItem> items) {
        this.items = items;
    }

    @NonNull
    @Override
    public ViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext())
                .inflate(R.layout.item_log, parent, false);
        return new ViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull ViewHolder holder, int position) {
        LogItem item = items.get(position);
        holder.tvMessage.setText(item.message);

        int textColor;
        int bgColor;
        switch (item.type) {
            case TYPE_REQUEST:
                textColor = Color.parseColor("#1565C0");
                bgColor = Color.parseColor("#E3F2FD");
                break;
            case TYPE_RESPONSE:
                textColor = Color.parseColor("#2E7D32");
                bgColor = Color.parseColor("#E8F5E9");
                break;
            case TYPE_ERROR:
                textColor = Color.parseColor("#C62828");
                bgColor = Color.parseColor("#FFEBEE");
                break;
            default:
                textColor = Color.DKGRAY;
                bgColor = Color.TRANSPARENT;
        }
        holder.tvMessage.setTextColor(textColor);
        holder.itemView.setBackgroundColor(bgColor);
    }

    @Override
    public int getItemCount() {
        return items.size();
    }

    static class ViewHolder extends RecyclerView.ViewHolder {
        TextView tvMessage;

        ViewHolder(View itemView) {
            super(itemView);
            tvMessage = itemView.findViewById(R.id.tv_log_message);
        }
    }
}
