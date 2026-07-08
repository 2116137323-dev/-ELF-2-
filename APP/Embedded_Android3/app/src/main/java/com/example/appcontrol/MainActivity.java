package com.example.appcontrol;

import androidx.core.app.ActivityCompat;
import androidx.appcompat.app.AppCompatActivity;

import android.Manifest;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.ActivityInfo;
import android.net.Uri;
import android.os.Bundle;
import android.view.MotionEvent;
import android.widget.Button;
import android.widget.ImageButton;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;

import org.videolan.libvlc.LibVLC;
import org.videolan.libvlc.Media;
import org.videolan.libvlc.MediaPlayer;
import org.videolan.libvlc.util.VLCVideoLayout;

public class MainActivity extends AppCompatActivity {

    private CarControlManager carManager;
    private CameraControlManager cameraManager;
    private IntercomManager intercomManager;

    // ==========================================
    // 一、配置参数 (热成像页面会自动同步这里的IP)
    // ==========================================
    private String serverIP   = NetworkConfig.SERVER_IP;
    private int    serverPort = NetworkConfig.SERVER_PORT;
    private String CAMERA_IP   = NetworkConfig.CAMERA_IP;

    // ==========================================
    // 二、控件与网络实例
    // ==========================================
    private Button bu_Send, btn_to_thermal, btn_alert_history;
    private ImageButton bu_up, bn_down, bn_right, bu_left,
            bu_up_camera, bu_dowm_camera,
            bu_left_camera, but_camera_right,
            bu_lamp, btn_enable_detection;
    private ImageButton btnTalk;
    private ImageButton btn_open_sound;
    private VLCVideoLayout vlcVideoLayout;
    private LibVLC libVLC;
    private MediaPlayer mediaPlayer;
    private SeekBar sp_speedBar;
    private TextView speedText;

    private boolean isLampOpen = false;

    private long lastPtzTime = 0;
    private static final long PTZ_THROTTLE_MS = 220;

    private boolean isReceiverRegistered = false;

    private BroadcastReceiver alertReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if ("com.example.appcontrol.ACTION_ALERT".equals(intent.getAction())) {
                String timestamp = intent.getStringExtra("timestamp");
                String status = intent.getStringExtra("status");
                AlertDialogManager.showAlertDialog(MainActivity.this, timestamp, status);
            }
        }
    };

    // ==========================================
    // 四、生命周期防断连管理
    // ==========================================
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE);

        // 【新增】：接收 LoginActivity 传过来的动态 IP
        Intent intent = getIntent();
        if (intent != null) {
            String passedCamIp = intent.getStringExtra("CAMERA_IP");
            String passedCarIp = intent.getStringExtra("CAR_IP");
            NetworkConfig.updateIps(passedCarIp, passedCamIp);

            // 同步本地变量
            serverIP = NetworkConfig.SERVER_IP;
            CAMERA_IP = NetworkConfig.CAMERA_IP;
        }

        initViews();
        initModules();
        initListeners();
        initPermissions();

        // 启动前台报警监听服务
        Intent serviceIntent = new Intent(this, AlertServerService.class);
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent);
        } else {
            startService(serviceIntent);
        }
        
        // 注册报警广播
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(alertReceiver, new IntentFilter("com.example.appcontrol.ACTION_ALERT"), Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(alertReceiver, new IntentFilter("com.example.appcontrol.ACTION_ALERT"));
        }
        isReceiverRegistered = true;

        // 不在这里 startVideo()，统一交由 onResume 管理
        carManager.initConnection(serverIP, serverPort);
    }

    private void initModules() {
        carManager = new CarControlManager();
        cameraManager = new CameraControlManager("admin", "123456");
        intercomManager = new IntercomManager(this, CAMERA_IP, NetworkConfig.RTSP_PORT, NetworkConfig.PATH_AUDIO_IN, NetworkConfig.PATH_AUDIO_OUT);
        intercomManager.setCallback(new IntercomManager.IntercomCallback() {
            @Override public void onListenStopped() { runOnUiThread(() -> btn_open_sound.setImageResource(R.drawable.gb)); }
            @Override public void onTalkStopped() { runOnUiThread(() -> btnTalk.setImageResource(R.drawable.mute)); }
            @Override public void onError(String message) {}
        });
    }

    @Override
    protected void onStart() {
        super.onStart();
        // 从热成像返回时，重新连接小车
        carManager.initConnection(serverIP, serverPort);
    }

    @Override
    protected void onResume() {
        super.onResume();
        // 【核心修复】：每次页面回到前台，先清理旧资源，再重新初始化视频流，解决黑屏和断连
        stopVideo();
        startVideo();
    }

    @Override
    protected void onPause() {
        super.onPause();
        // 【核心修复】：离开页面时，彻底释放视频资源，避免占用底层解码器和网络通道
        stopVideo();
    }

    @Override
    protected void onStop() {
        super.onStop();
        AlertDialogManager.dismissForActivity(this);
        // 【核心】：去热成像页面时，必须释放所有 Socket 端口，解决断连问题
        if (intercomManager != null) {
            intercomManager.stopListen();
            intercomManager.stopTalk();
        }
        if (carManager != null) carManager.closeConnection();

        if (btn_open_sound != null) btn_open_sound.setImageResource(R.drawable.gb);
        if (btnTalk != null) btnTalk.setImageResource(R.drawable.mute);
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        AlertDialogManager.dismissForActivity(this);
        stopVideo();
        if (intercomManager != null) {
            intercomManager.stopListen();
            intercomManager.stopTalk();
        }
        if (carManager != null) carManager.closeConnection();
        if (isReceiverRegistered) {
            try {
                unregisterReceiver(alertReceiver);
            } catch (Exception ignored) {}
            isReceiverRegistered = false;
        }
    }

    // ==========================================
    // 视频播放控制
    // ==========================================
    private void startVideo() {
        if (vlcVideoLayout == null || mediaPlayer != null) return;
        try {
            libVLC = new LibVLC(this);
            mediaPlayer = new MediaPlayer(libVLC);
            mediaPlayer.attachViews(vlcVideoLayout, null, false, false);

            // 【修改】：使用动态方法获取最新的视频流地址
            Media media = new Media(libVLC, android.net.Uri.parse(NetworkConfig.getVideoUrl(CAMERA_IP)));

            // 尽量压低 RTSP 起播等待时间，优先首帧速度。
            media.setHWDecoderEnabled(true, false);
            media.addOption(":network-caching=120");
            media.addOption(":live-caching=80");
            media.addOption(":rtsp-tcp");
            media.addOption(":no-audio");
            media.addOption(":clock-jitter=0");
            media.addOption(":clock-synchro=0");
            media.addOption(":drop-late-frames");
            media.addOption(":skip-frames");

            mediaPlayer.setMedia(media);
            mediaPlayer.play();
            media.release();
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    /**
     * 【新增】：彻底清理视频资源，解决返回黑屏问题的核心
     */
    private void stopVideo() {
        try {
            if (mediaPlayer != null) {
                mediaPlayer.stop();
                mediaPlayer.detachViews(); // 关键：脱离视图画布
                mediaPlayer.release();
                // 关键：释放底层播放器
                mediaPlayer = null;
            }
            if (libVLC != null) {
                libVLC.release();
                // 关键：释放 LibVLC 实例
                libVLC = null;
            }
        } catch (Exception e) {
            e.printStackTrace();
            mediaPlayer = null;
            libVLC = null;
        }
    }

    // ==========================================
    // 初始化逻辑
    // ==========================================
    private void initViews() {
        speedText         = findViewById(R.id.textView);
        bu_lamp           = findViewById(R.id.lamp_off);
        bu_up             = findViewById(R.id.btn_up);
        bn_down           = findViewById(R.id.btn_down);
        bn_right          = findViewById(R.id.btn_right);
        bu_left           = findViewById(R.id.btn_left);
        bu_Send           = findViewById(R.id.Send);
        bu_up_camera      = findViewById(R.id.btn_onthecamera);
        bu_dowm_camera    = findViewById(R.id.btn_underthecamera);
        bu_left_camera    = findViewById(R.id.btn_cameraleft);
        but_camera_right  = findViewById(R.id.btn_cameraright);
        sp_speedBar       = findViewById(R.id.speedBar);
        btnTalk           = findViewById(R.id.btn_talk);
        btn_open_sound    = findViewById(R.id.btn_open_sound);
        vlcVideoLayout    = findViewById(R.id.vlc_video_layout);

        btn_to_thermal    = findViewById(R.id.btn_navigate);
        btn_alert_history = findViewById(R.id.btn_alert_history);
        btn_enable_detection = findViewById(R.id.btn_enable_detection);
    }

    private void initListeners() {
        // 跳转到热成像界面（动态传递 IP）
        if (btn_to_thermal != null) {
            btn_to_thermal.setOnClickListener(v -> {
                Intent intent = new Intent(MainActivity.this, Thermal_imaging.class);
                intent.putExtra("CAR_IP", serverIP);
                intent.putExtra("CAMERA_IP", CAMERA_IP);
                startActivity(intent);
            });
        }

        if (btn_alert_history != null) {
            btn_alert_history.setOnClickListener(v -> {
                Intent intent = new Intent(MainActivity.this, AlertHistoryActivity.class);
                startActivity(intent);
            });
        }

        if (btn_enable_detection != null) {
            btn_enable_detection.setOnClickListener(v ->
                    DetectionControlManager.startDetection(MainActivity.this));
        }

        // 小车移动控制
        bu_up.setOnTouchListener((v,en)->{
            if (en.getAction()==MotionEvent.ACTION_DOWN)
                carManager.sendToCar(serverIP, serverPort, "w");
            else if (en.getAction()==MotionEvent.ACTION_UP)
                carManager.sendToCar(serverIP, serverPort, "0");
            return true;
        });
        bn_down.setOnTouchListener((v,en)->{
            if (en.getAction()==MotionEvent.ACTION_DOWN)
                carManager.sendToCar(serverIP, serverPort, "s");
            else if (en.getAction()==MotionEvent.ACTION_UP)
                carManager.sendToCar(serverIP, serverPort, "0");
            return true;
        });
        bn_right.setOnTouchListener((v,en)->{
            if (en.getAction()==MotionEvent.ACTION_DOWN) {
                carManager.sendToCar(serverIP, serverPort, "d");
            } else if (en.getAction()==MotionEvent.ACTION_UP) {
                carManager.sendToCar(serverIP, serverPort, "0");
            }
            return true;
        });
        if (bu_left != null) {
            bu_left.setOnTouchListener((v,en)->{
                if (en.getAction()==MotionEvent.ACTION_DOWN)
                    carManager.sendToCar(serverIP, serverPort, "a");
                else if (en.getAction()==MotionEvent.ACTION_UP)
                    carManager.sendToCar(serverIP, serverPort, "0");
                return true;
            });
        }

        // 云台方向控制
        bu_up_camera.setOnTouchListener((v,en)->{
            if (en.getAction()==MotionEvent.ACTION_DOWN) {
                long now = System.currentTimeMillis();
                if (now - lastPtzTime > PTZ_THROTTLE_MS) {
                    lastPtzTime = now;
                    cameraManager.ptzControl(NetworkConfig.getPtzUrl(CAMERA_IP), 21, 0);
                }
            } else if (en.getAction()==MotionEvent.ACTION_UP) {
                cameraManager.ptzControl(NetworkConfig.getPtzUrl(CAMERA_IP), 21, 1);
            }
            return true;
        });
        bu_dowm_camera.setOnTouchListener((v,en)->{
            if (en.getAction()==MotionEvent.ACTION_DOWN) {
                long now = System.currentTimeMillis();
                if (now - lastPtzTime > PTZ_THROTTLE_MS) {
                    lastPtzTime = now;
                    cameraManager.ptzControl(NetworkConfig.getPtzUrl(CAMERA_IP), 22, 0);
                }
            } else if (en.getAction()==MotionEvent.ACTION_UP) {
                cameraManager.ptzControl(NetworkConfig.getPtzUrl(CAMERA_IP), 22, 1);
            }
            return true;
        });
        bu_left_camera.setOnTouchListener((v,en)->{
            if (en.getAction()==MotionEvent.ACTION_DOWN) {
                long now = System.currentTimeMillis();
                if (now - lastPtzTime > PTZ_THROTTLE_MS) {
                    lastPtzTime = now;
                    cameraManager.ptzControl(NetworkConfig.getPtzUrl(CAMERA_IP), 23, 0);
                }
            } else if (en.getAction()==MotionEvent.ACTION_UP) {
                cameraManager.ptzControl(NetworkConfig.getPtzUrl(CAMERA_IP), 23, 1);
            }
            return true;
        });
        but_camera_right.setOnTouchListener((v,en)->{
            if (en.getAction()==MotionEvent.ACTION_DOWN) {
                long now = System.currentTimeMillis();
                if (now - lastPtzTime > PTZ_THROTTLE_MS) {
                    lastPtzTime = now;
                    cameraManager.ptzControl(NetworkConfig.getPtzUrl(CAMERA_IP), 24, 0);
                }
            } else if (en.getAction()==MotionEvent.ACTION_UP) {
                cameraManager.ptzControl(NetworkConfig.getPtzUrl(CAMERA_IP), 24, 1);
            }
            return true;
        });
        // 调速
        bu_Send.setOnClickListener(v->{
            int sp = sp_speedBar.getProgress();
            speedText.setText("当前时速："+sp);
            carManager.sendToCar(serverIP, serverPort, String.valueOf(sp));
        });
        // 声音与灯光
        btn_open_sound.setOnClickListener(v->toggleAudioListen());
        btnTalk.setOnClickListener(v->toggleAudioTalk());
        bu_lamp.setOnClickListener(v->control_lamp());
    }

    private void initPermissions() {
        ActivityCompat.requestPermissions(this,
                new String[]{Manifest.permission.RECORD_AUDIO, Manifest.permission.INTERNET}, 100);
    }

    // ==========================================
    // 界面业务动作切换
    // ==========================================
    private void toggleAudioListen(){
        if (!intercomManager.isListening()) {
            intercomManager.startListen();
            btn_open_sound.setImageResource(R.drawable.k);
            Toast.makeText(this,"已打开监听",Toast.LENGTH_SHORT).show();
        } else {
            intercomManager.stopListen();
            btn_open_sound.setImageResource(R.drawable.gb);
            Toast.makeText(this,"已关闭监听",Toast.LENGTH_SHORT).show();
        }
    }

    private void toggleAudioTalk(){
        if (!intercomManager.isTalking()) {
            intercomManager.startTalk();
            btnTalk.setImageResource(R.drawable.mic);
            Toast.makeText(this,"对讲中",Toast.LENGTH_SHORT).show();
        } else {
            intercomManager.stopTalk();
            btnTalk.setImageResource(R.drawable.mute);
            Toast.makeText(this,"对讲结束",Toast.LENGTH_SHORT).show();
        }
    }

    private void control_lamp() {
        isLampOpen = !isLampOpen;
        if (isLampOpen) {
            cameraManager.lightControl(NetworkConfig.getLightUrl(CAMERA_IP), 1);
            bu_lamp.setImageResource(R.drawable.lamp_open);
        } else {
            cameraManager.lightControl(NetworkConfig.getLightUrl(CAMERA_IP), 0);
            bu_lamp.setImageResource(R.drawable.lamp_off);
        }
    }
}
