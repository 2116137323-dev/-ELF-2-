package com.example.appcontrol;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Bundle;
import android.util.Log;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * 报警历史记录页面。
 *
 * 从应用外部私有目录 alerts 中扫描报警图片，根据时间戳合并热成像图和可见光图，
 * 并提供确认、查看和清空历史记录功能。
 */
public class AlertHistoryActivity extends AppCompatActivity {

    private ListView listView;
    private AlertAdapter adapter;
    private List<AlertItem> alertList = new ArrayList<>();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_alert_history);

        listView = findViewById(R.id.alertListView);
        Button btnClear = findViewById(R.id.btnClear);

        adapter = new AlertAdapter();
        listView.setAdapter(adapter);

        loadAlerts();

        btnClear.setOnClickListener(v -> {
            clearAlerts();
        });
    }

    /**
     * 扫描本地报警图片目录，并按时间倒序生成列表数据。
     *
     * 文件命名规则：{timestamp}_thermal.jpg 与 {timestamp}_camera.jpg。
     */
    private void loadAlerts() {
        alertList.clear();
        File dir = new File(getExternalFilesDir(null), "alerts");
        if (dir.exists() && dir.isDirectory()) {
            File[] files = dir.listFiles();
            if (files != null) {
                Set<String> timestampsSet = new HashSet<>();
                for (File f : files) {
                    String name = f.getName();
                    if (name.endsWith("_thermal.jpg")) {
                        timestampsSet.add(name.replace("_thermal.jpg", ""));
                    } else if (name.endsWith("_camera.jpg")) {
                        timestampsSet.add(name.replace("_camera.jpg", ""));
                    }
                }
                List<String> timestamps = new ArrayList<>(timestampsSet);
                Collections.sort(timestamps, Collections.reverseOrder());
                for (String ts : timestamps) {
                    boolean confirmed = AlertDialogManager.isConfirmed(this, ts);
                    alertList.add(new AlertItem(ts, 
                        new File(dir, ts + "_thermal.jpg").getAbsolutePath(),
                        new File(dir, ts + "_camera.jpg").getAbsolutePath(),
                        confirmed));
                }
            }
        }
        adapter.notifyDataSetChanged();
    }

    /**
     * 清空历史报警图片。
     *
     * 为防止误删未处理报警，只要存在未确认记录，就禁止清空。
     */
    private void clearAlerts() {
        File dir = new File(getExternalFilesDir(null), "alerts");
        if (dir.exists()) {
            File[] files = dir.listFiles();
            if (files != null) {
                boolean hasUnconfirmed = false;
                for (AlertItem item : alertList) {
                    if (!item.confirmed) {
                        hasUnconfirmed = true;
                        break;
                    }
                }
                if (hasUnconfirmed) {
                    Toast.makeText(this, "存在未确认记录，无法清空", Toast.LENGTH_SHORT).show();
                    return;
                }

                for (File f : files) f.delete();
            }
        }
        alertList.clear();
        adapter.notifyDataSetChanged();
        Toast.makeText(this, "记录已清空", Toast.LENGTH_SHORT).show();
    }

    /**
     * 单条报警历史的数据模型。
     */
    private static class AlertItem {
        String timestamp;
        String thermalPath;
        String cameraPath;
        boolean confirmed;

        AlertItem(String timestamp, String thermalPath, String cameraPath, boolean confirmed) {
            this.timestamp = timestamp;
            this.thermalPath = thermalPath;
            this.cameraPath = cameraPath;
            this.confirmed = confirmed;
        }
    }

    /**
     * ListView 适配器：负责把 AlertItem 渲染成 item_alert 布局。
     */
    private class AlertAdapter extends BaseAdapter {
        @Override
        public int getCount() { return alertList.size(); }
        @Override
        public Object getItem(int position) { return alertList.get(position); }
        @Override
        public long getItemId(int position) { return position; }

        @Override
        public View getView(int position, View convertView, ViewGroup parent) {
            if (convertView == null) {
                convertView = LayoutInflater.from(AlertHistoryActivity.this).inflate(R.layout.item_alert, parent, false);
            }
            AlertItem item = alertList.get(position);
            TextView tvTime = convertView.findViewById(R.id.tvTime);
            TextView tvThermalHint = convertView.findViewById(R.id.tvThermalHint);
            ImageView ivThermal = convertView.findViewById(R.id.ivThermal);
            ImageView ivCamera = convertView.findViewById(R.id.ivCamera);
            Button btnConfirm = convertView.findViewById(R.id.btnConfirm);

            tvTime.setText("报警时间: " + item.timestamp);
            
            // 加载图片并增加空处理
            Bitmap bmThermal = decodeSampledBitmap(item.thermalPath, 400, 300);
            if (bmThermal != null) {
                ivThermal.setImageBitmap(bmThermal);
                ivThermal.setVisibility(View.VISIBLE);
                if (tvThermalHint != null) tvThermalHint.setVisibility(View.GONE);
            } else {
                ivThermal.setImageDrawable(null);
                ivThermal.setVisibility(View.INVISIBLE);
                if (tvThermalHint != null) tvThermalHint.setVisibility(View.VISIBLE);
            }

            Bitmap bmCamera = decodeSampledBitmap(item.cameraPath, 400, 300);
            if (bmCamera != null) {
                ivCamera.setImageBitmap(bmCamera);
            } else {
                ivCamera.setImageResource(android.R.drawable.ic_menu_report_image); // 错误图标
                Log.e("AlertHistory", "Failed to load camera image: " + item.cameraPath);
            }

            if (btnConfirm != null) {
                btnConfirm.setEnabled(!item.confirmed);
                btnConfirm.setText(item.confirmed ? "已确认" : "确认");
                btnConfirm.setOnClickListener(v -> {
                    if (!item.confirmed) {
                        AlertDialogManager.confirmAlert(AlertHistoryActivity.this, item.timestamp);
                        item.confirmed = true;
                        notifyDataSetChanged();
                    }
                });
            }

            return convertView;
        }

        /**
         * 按目标尺寸采样加载图片，降低报警图片过大导致的内存占用。
         */
        private Bitmap decodeSampledBitmap(String path, int reqWidth, int reqHeight) {
            final BitmapFactory.Options options = new BitmapFactory.Options();
            options.inJustDecodeBounds = true;
            BitmapFactory.decodeFile(path, options);
            options.inSampleSize = calculateInSampleSize(options, reqWidth, reqHeight);
            options.inJustDecodeBounds = false;
            return BitmapFactory.decodeFile(path, options);
        }

        /**
         * 计算 BitmapFactory 的 inSampleSize，取 2 的倍数以兼容 Android 高效采样规则。
         */
        private int calculateInSampleSize(BitmapFactory.Options options, int reqWidth, int reqHeight) {
            final int height = options.outHeight;
            final int width = options.outWidth;
            int inSampleSize = 1;
            if (height > reqHeight || width > reqWidth) {
                final int halfHeight = height / 2;
                final int halfWidth = width / 2;
                while ((halfHeight / inSampleSize) >= reqHeight && (halfWidth / inSampleSize) >= reqWidth) {
                    inSampleSize *= 2;
                }
            }
            return inSampleSize;
        }
    }
}
