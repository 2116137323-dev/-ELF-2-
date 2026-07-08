package com.example.appcontrol;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.media.AudioAttributes;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.util.Log;
import android.widget.Toast;

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;

import fi.iki.elonen.NanoHTTPD;

import java.io.File;
import java.io.IOException;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;

public class AlertServerService extends Service {
    private static final String TAG = "AlertServerService";
    private static final int PORT = 8080;
    private static final String CHANNEL_ID = "AlertServiceChannel";
    private WebServer server;
    private Handler mainHandler = new Handler(Looper.getMainLooper());
    private MediaPlayer currentPlayer;
    private final Handler audioHandler = new Handler(Looper.getMainLooper());

    @Override
    public void onCreate() {
        super.onCreate();
        Log.d(TAG, "onCreate: Service is creating");
        createNotificationChannel();
        startForeground(1, getServiceNotification("报警监听服务已启动"));
        
        server = new WebServer(PORT);
        try {
            server.start();
            Log.d(TAG, "Server started on port " + PORT);
            Toast.makeText(this, "报警监听服务已就绪 (8080)", Toast.LENGTH_SHORT).show();
        } catch (IOException e) {
            Log.e(TAG, "Server failed to start", e);
            Toast.makeText(this, "报警服务启动失败: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel serviceChannel = new NotificationChannel(
                    CHANNEL_ID,
                    "Alert Service Channel",
                    NotificationManager.IMPORTANCE_LOW
            );
            NotificationManager manager = getSystemService(NotificationManager.class);
            manager.createNotificationChannel(serviceChannel);
        }
    }

    private Notification getServiceNotification(String content) {
        return new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("搜救机器人")
                .setContentText(content)
                .setSmallIcon(R.drawable.desktop)
                .build();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Log.d(TAG, "onStartCommand: Service is started");
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        Log.d(TAG, "onDestroy: Service is destroying");
        super.onDestroy();
        if (server != null) {
            server.stop();
        }
        stopCurrentAudio();
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private class WebServer extends NanoHTTPD {
        public WebServer(int port) {
            super(port);
        }

        @Override
        public Response serve(IHTTPSession session) {
            Log.d(TAG, "Receive request: " + session.getMethod() + " " + session.getUri());
            
            if (Method.POST.equals(session.getMethod()) && "/upload".equals(session.getUri())) {
                try {
                    Map<String, String> files = new HashMap<>();
                    session.parseBody(files);
                    
                    Log.d(TAG, "Uploaded files: " + files.keySet());

                    Map<String, String> params = session.getParms();
                    String timestamp = params.get("timestamp");
                    if (timestamp == null) timestamp = String.valueOf(System.currentTimeMillis());
                    String status = params.get("status");

                    // 获取保存路径
                    File dir = new File(getExternalFilesDir(null), "alerts");
                    if (!dir.exists()) dir.mkdirs();

                    boolean thermalSaved = false;
                    boolean cameraSaved = false;

                    // 调试：打印所有收到的 key 和参数
                    Log.d(TAG, "All files keys: " + files.keySet());
                    Log.d(TAG, "All params: " + params.keySet());

                    // 1. 优先通过 key 直接获取
                    String thermalTmp = files.get("thermal");
                    if (thermalTmp == null) thermalTmp = files.get("thermal.jpg");
                    
                    String cameraTmp = files.get("camera");
                    if (cameraTmp == null) cameraTmp = files.get("camera.jpg");

                    // 2. 如果 key 匹配失败，遍历所有收到的临时文件进行保存
                    if (thermalTmp == null || cameraTmp == null) {
                        for (Map.Entry<String, String> entry : files.entrySet()) {
                            String key = entry.getKey().toLowerCase();
                            String tmpPath = entry.getValue();
                            
                            if (thermalTmp == null && (key.contains("thermal") || key.equals("file1"))) {
                                thermalTmp = tmpPath;
                                Log.d(TAG, "Auto-detected thermal file from key: " + key);
                            } else if (cameraTmp == null && (key.contains("camera") || key.equals("file2"))) {
                                cameraTmp = tmpPath;
                                Log.d(TAG, "Auto-detected camera file from key: " + key);
                            }
                        }
                    }

                    // 3. 执行物理保存
                    if (thermalTmp != null) {
                        File target = new File(dir, timestamp + "_thermal.jpg");
                        saveFile(new File(thermalTmp), target);
                        thermalSaved = target.exists() && target.length() > 0;
                        Log.d(TAG, "Thermal save result: " + thermalSaved + ", size: " + target.length());
                    }

                    if (cameraTmp != null) {
                        File target = new File(dir, timestamp + "_camera.jpg");
                        saveFile(new File(cameraTmp), target);
                        cameraSaved = target.exists() && target.length() > 0;
                        Log.d(TAG, "Camera save result: " + cameraSaved + ", size: " + target.length());
                    }

                    if (thermalSaved || cameraSaved) {
                        triggerAlarm(timestamp, status);
                        return newFixedLengthResponse(Response.Status.OK, MIME_PLAINTEXT, "Upload successful");
                    } else {
                        Log.e(TAG, "No valid images saved. files count: " + files.size());
                        return newFixedLengthResponse(Response.Status.BAD_REQUEST, MIME_PLAINTEXT, "No images found");
                    }
                } catch (Exception e) {
                    Log.e(TAG, "Upload processing failed", e);
                    return newFixedLengthResponse(Response.Status.INTERNAL_ERROR, MIME_PLAINTEXT, "Error: " + e.getMessage());
                }
            }
            return newFixedLengthResponse(Response.Status.NOT_FOUND, MIME_PLAINTEXT, "Route not found");
        }

        private void saveFile(File src, File dst) throws IOException {
            try (java.nio.channels.FileChannel in = new java.io.FileInputStream(src).getChannel();
                 java.nio.channels.FileChannel out = new java.io.FileOutputStream(dst).getChannel()) {
                in.transferTo(0, in.size(), out);
            }
        }
    }

    private void triggerAlarm(String timestamp, @Nullable String status) {
        mainHandler.post(() -> {
            Log.d(TAG, "Triggering alarm UI and sound for: " + timestamp);
            String toastMsg;
            if ("dual_detected".equals(status)) {
                toastMsg = "⚠️ 活体报警！已抓拍并报警...";
            } else if ("camera_detected".equals(status)) {
                toastMsg = "⚠️ 死亡报警！已抓拍并报警...";
            } else if ("amputated_limb_with_temperature".equals(status)) {
                toastMsg = "⚠️ 残肢报警！已抓拍并报警...";
            } else if ("amputated_limb_no_temperature".equals(status)) {
                toastMsg = "⚠️ 断肢报警！已抓拍并报警...";
            } else {
                toastMsg = "⚠️ 发现异常目标！正在报警...";
            }
            Toast.makeText(getApplicationContext(), toastMsg, Toast.LENGTH_LONG).show();
            
            // 播放报警音
            playAlarmSound(timestamp, status);
            
            // 发送广播通知 Activity 显示弹窗
            Intent intent = new Intent("com.example.appcontrol.ACTION_ALERT");
            intent.putExtra("timestamp", timestamp);
            intent.putExtra("status", status);
            intent.setPackage(getPackageName());
            sendBroadcast(intent);
        });
    }

    private void stopCurrentAudio() {
        audioHandler.removeCallbacksAndMessages(null);
        if (currentPlayer != null) {
            try {
                if (currentPlayer.isPlaying()) currentPlayer.stop();
            } catch (Exception ignored) {}
            try {
                currentPlayer.release();
            } catch (Exception ignored) {}
            currentPlayer = null;
        }
    }

    private int getStatusAudioResId(@Nullable String status) {
        String[] candidates;
        if ("dual_detected".equals(status)) {
            candidates = new String[]{"alarm_alive", "alarm_dual_detected"};
        } else if ("camera_detected".equals(status)) {
            candidates = new String[]{"alarm_dead", "alarm_camera_detected"};
        } else if ("amputated_limb_with_temperature".equals(status)) {
            candidates = new String[]{"alarm_limb_hot", "alarm_amputated_limb_with_temperature"};
        } else if ("amputated_limb_no_temperature".equals(status)) {
            candidates = new String[]{"alarm_limb_cold", "alarm_amputated_limb_no_temperature"};
        } else {
            candidates = new String[]{"alarm"};
        }

        for (String name : candidates) {
            int resId = getResources().getIdentifier(name, "raw", getPackageName());
            if (resId != 0) return resId;
        }

        return getResources().getIdentifier("alarm", "raw", getPackageName());
    }

    private void playAlarmSound(String timestamp, @Nullable String status) {
        try {
            stopCurrentAudio();
            AudioManager audioManager = (AudioManager) getSystemService(Context.AUDIO_SERVICE);
            if (audioManager != null) {
                int maxVolume = audioManager.getStreamMaxVolume(AudioManager.STREAM_ALARM);
                int targetVolume = (int) (maxVolume * 0.7);
                audioManager.setStreamVolume(AudioManager.STREAM_ALARM, targetVolume, 0);
                Log.d(TAG, "Alarm volume set to moderate: " + targetVolume);
            }

            MediaPlayer mp = new MediaPlayer();
            currentPlayer = mp;
            int resId = getStatusAudioResId(status);
            if (resId != 0) {
                Uri customUri = Uri.parse("android.resource://" + getPackageName() + "/" + resId);
                mp.setDataSource(getApplicationContext(), customUri);
            } else {
                Uri alert = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM);
                if (alert == null) alert = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE);
                if (alert == null) alert = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION);
                mp.setDataSource(getApplicationContext(), alert);
            }

            AudioAttributes attributes = new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build();
            mp.setAudioAttributes(attributes);
            mp.setVolume(0.8f, 0.8f);
            mp.setLooping(false);
            mp.prepare();
            mp.start();
            mp.setOnCompletionListener(player -> stopCurrentAudio());
            audioHandler.postDelayed(this::stopCurrentAudio, 15000);
        } catch (Exception e) {
            Log.e(TAG, "Failed to play alarm sound: " + e.getMessage());
        }
    }
}
