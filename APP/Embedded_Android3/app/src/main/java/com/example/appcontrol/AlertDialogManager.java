package com.example.appcontrol;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.widget.Toast;
import android.view.WindowManager;

import androidx.annotation.Nullable;

import java.io.File;
import java.io.IOException;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.FormBody;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

final class AlertDialogManager {
    private static AlertDialog currentDialog;
    private static Activity currentOwner;
    private static final OkHttpClient ACK_CLIENT = new OkHttpClient();

    private AlertDialogManager() {}

    static void showAlertDialog(Activity activity, String timestamp, @Nullable String status) {
        // 防止 Activity 不在前台/已销毁时弹窗导致 BadTokenException 闪退
        if (activity == null || activity.isFinishing() || activity.isDestroyed()) {
            return;
        }

        dismissCurrentDialog();

        String title;
        String message;
        if ("dual_detected".equals(status)) {
            title = "⚠️ 被困报警";
            message = "疑似被困人员。时间：" + timestamp;
        } else if ("camera_detected".equals(status)) {
            title = "⚠️ 死亡报警";
            message = "疑似死亡。时间：" + timestamp;
        } else if ("amputated_limb_with_temperature".equals(status)) {
            title = "⚠️ 肢体报警";
            message = "疑似肢体附近存在遇害人员。时间：" + timestamp;
        } else if ("amputated_limb_no_temperature".equals(status)) {
            title = "⚠️ 残肢报警";
            message = "疑似残肢。时间：" + timestamp;
        } else {
            title = "⚠️ 人体检测报警";
            message = "发现目标！已抓拍照片！时间：" + timestamp;
        }

        AlertDialog dialog = new AlertDialog.Builder(activity)
                .setTitle(title)
                .setMessage(message)
                .setPositiveButton("查看照片", (d, which) -> activity.startActivity(
                        new android.content.Intent(activity, AlertHistoryActivity.class)))
                .setNeutralButton("确认", (d, which) -> confirmAlert(activity, timestamp))
                .setNegativeButton("忽略", null)
                .setCancelable(false)
                .create();

        currentOwner = activity;
        currentDialog = dialog;

        dialog.setOnDismissListener(d -> {
            if (currentDialog == dialog) {
                currentDialog = null;
                currentOwner = null;
            }
        });

        try {
            dialog.show();
        } catch (Exception e) {
            // Activity 窗口已失效等极端情况，避免崩溃
            currentDialog = null;
            currentOwner = null;
            return;
        }

        if (dialog.getWindow() != null) {
            WindowManager.LayoutParams lp = new WindowManager.LayoutParams();
            lp.copyFrom(dialog.getWindow().getAttributes());
            lp.width = (int) (activity.getResources().getDisplayMetrics().widthPixels * 0.6);
            lp.height = WindowManager.LayoutParams.WRAP_CONTENT;
            dialog.getWindow().setAttributes(lp);
        }
    }

    static void dismissForActivity(Activity activity) {
        if (currentOwner == activity) {
            dismissCurrentDialog();
        }
    }

    static void confirmAlert(Context context, String timestamp) {
        markConfirmed(context, timestamp);
        sendAck(context, timestamp);
        Toast.makeText(context.getApplicationContext(), "已确认", Toast.LENGTH_SHORT).show();
    }

    static boolean isConfirmed(Context context, String timestamp) {
        File dir = new File(context.getExternalFilesDir(null), "alerts");
        File f = new File(dir, timestamp + ".confirmed");
        return f.exists();
    }

    private static void markConfirmed(Context context, String timestamp) {
        File dir = new File(context.getExternalFilesDir(null), "alerts");
        if (!dir.exists()) dir.mkdirs();
        File f = new File(dir, timestamp + ".confirmed");
        if (!f.exists()) {
            try {
                f.createNewFile();
            } catch (IOException ignored) {}
        }
    }

    private static void sendAck(Context context, String timestamp) {
        String url = NetworkConfig.getAckUrl(NetworkConfig.SERVER_IP);
        RequestBody body = new FormBody.Builder()
                .add("timestamp", timestamp)
                .build();
        Request req = new Request.Builder().url(url).post(body).build();
        ACK_CLIENT.newCall(req).enqueue(new Callback() {
            @Override public void onFailure(Call call, IOException e) {}
            @Override public void onResponse(Call call, Response response) throws IOException { response.close(); }
        });
    }

    private static void dismissCurrentDialog() {
        if (currentDialog != null) {
            AlertDialog dialog = currentDialog;
            currentDialog = null;
            currentOwner = null;
            try {
                if (dialog.isShowing()) {
                    dialog.dismiss();
                }
            } catch (Exception ignored) {}
        }
    }
}
