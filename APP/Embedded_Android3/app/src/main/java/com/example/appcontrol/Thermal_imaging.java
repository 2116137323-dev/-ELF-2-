package com.example.appcontrol;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;

import android.Manifest;
import android.annotation.SuppressLint;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.ActivityInfo;
import android.os.Bundle;
import android.view.MotionEvent;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.ImageButton;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;

/**
 * 热成像主控制页面。
 *
 * 页面职责：
 * - 显示 RK3588 Flask 发布的热成像/可见光 Web 页面。
 * - 控制小车前后左右与速度。
 * - 控制摄像头补光灯。
 * - 开启摄像头监听/对讲。
 * - 接收报警广播并弹出报警确认窗口。
 */
public class Thermal_imaging extends AppCompatActivity {

    private CarControlManager carManager;
    private CameraControlManager cameraManager;
    private IntercomManager intercomManager;

    // 本页面使用的网络参数，初始化时从 NetworkConfig 同步，入口传参可覆盖默认 IP。
    private String serverIP = NetworkConfig.SERVER_IP;
    private int serverPort = NetworkConfig.SERVER_PORT;
    private String cameraIP = NetworkConfig.CAMERA_IP;

    private Button bu_Send, btn_navigate, btn_alert_history;
    private ImageButton bu_up, bn_down, bn_right, bu_left, bu_lamp, btnTalk, btn_open_sound, btn_enable_detection;
    private WebView webThermalVideo;
    // 灯光状态可能由点击事件快速切换，volatile 保证不同线程读取到最新值。
    private volatile boolean isLampOpen = false;
    private boolean isReceiverRegistered = false;

    // 后台报警服务保存图片后会发送本地广播，页面收到后弹出报警确认窗口。
    private BroadcastReceiver alertReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if ("com.example.appcontrol.ACTION_ALERT".equals(intent.getAction())) {
                String timestamp = intent.getStringExtra("timestamp");
                String status = intent.getStringExtra("status");
                AlertDialogManager.showAlertDialog(Thermal_imaging.this, timestamp, status);
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_thermal_imaging);
        setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE);

        if (getIntent() != null) {
            String passedCarIp = getIntent().getStringExtra("CAR_IP");
            String passedCamIp = getIntent().getStringExtra("CAMERA_IP");
            NetworkConfig.updateIps(passedCarIp, passedCamIp);

            // 同步本地变量
            serverIP = NetworkConfig.SERVER_IP;
            cameraIP = NetworkConfig.CAMERA_IP;
        }

        initViews();
        initModules();
        initListeners();
        initPermissions();
        startThermalWebVideo();

        // 注册报警广播
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(alertReceiver, new IntentFilter("com.example.appcontrol.ACTION_ALERT"), Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(alertReceiver, new IntentFilter("com.example.appcontrol.ACTION_ALERT"));
        }
        isReceiverRegistered = true;
    }

    /**
     * 初始化业务管理类：小车 TCP 控制、摄像头 HTTP 控制、RTSP 对讲。
     */
    private void initModules() {
        carManager = new CarControlManager();
        cameraManager = new CameraControlManager("admin", "123456");
        intercomManager = new IntercomManager(this, cameraIP, NetworkConfig.RTSP_PORT, NetworkConfig.PATH_AUDIO_IN, NetworkConfig.PATH_AUDIO_OUT);
        intercomManager.setCallback(new IntercomManager.IntercomCallback() {
            @Override public void onListenStopped() { runOnUiThread(() -> btn_open_sound.setImageResource(R.drawable.gb)); }
            @Override public void onTalkStopped() { runOnUiThread(() -> btnTalk.setImageResource(R.drawable.mute)); }
            @Override public void onError(String message) {}
        });
    }

    @Override
    protected void onStart() {
        super.onStart();
        carManager.initConnection(serverIP, serverPort);
    }

    @Override
    protected void onStop() {
        super.onStop();
        AlertDialogManager.dismissForActivity(this);
        // 离开当前页面时立马切断，不占通道，保证主页面回去时秒连
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
        if (webThermalVideo != null) {
            try {
                webThermalVideo.loadDataWithBaseURL(null, "", "text/html", "utf-8", null);
                webThermalVideo.clearHistory();
                webThermalVideo.destroy();
            } catch (Exception ignored) {}
            webThermalVideo = null;
        }
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
    // 热成像视频流 (WebView 加载固定发布网页)
    // ==========================================
    @SuppressLint("SetJavaScriptEnabled")
    private void startThermalWebVideo() {
        if (webThermalVideo == null) return;
        WebSettings webSettings = webThermalVideo.getSettings();
        webSettings.setJavaScriptEnabled(true);
        webSettings.setUseWideViewPort(true);
        webSettings.setLoadWithOverviewMode(true);
        webSettings.setDomStorageEnabled(true);
        webSettings.setBuiltInZoomControls(false);

        webThermalVideo.setWebViewClient(new WebViewClient());
        // 固定的热成像发布网页地址
        webThermalVideo.loadUrl(NetworkConfig.THERMAL_WEB_URL);
    }

    /**
     * 绑定布局中的控件，后续统一在 initListeners() 中设置事件。
     */
    private void initViews() {
        bu_lamp           = findViewById(R.id.lamp_off);
        bu_up             = findViewById(R.id.btn_up);
        bn_down           = findViewById(R.id.btn_down);
        bn_right          = findViewById(R.id.btn_right);
        bu_left           = findViewById(R.id.btn_left);
        bu_Send           = findViewById(R.id.Send);
        btn_navigate      = findViewById(R.id.btn_navigate);
        btnTalk           = findViewById(R.id.btn_talk);
        btn_open_sound    = findViewById(R.id.btn_open_sound);
        webThermalVideo   = findViewById(R.id.web_thermal_view);
        btn_alert_history = findViewById(R.id.btn_alert_history);
        btn_enable_detection = findViewById(R.id.btn_enable_detection);
    }

    /**
     * 设置所有按钮事件：方向按钮按下发送运动命令，抬起发送停止命令。
     */
    @SuppressLint("ClickableViewAccessibility")
    private void initListeners() {
        // 添加判空保护
        if (bu_up != null) {
            bu_up.setOnTouchListener((v,en)->{
                if (en.getAction()==MotionEvent.ACTION_DOWN) carManager.sendToCar(serverIP, serverPort, "w");
                else if (en.getAction()==MotionEvent.ACTION_UP) carManager.sendToCar(serverIP, serverPort, "0");
                return true;
            });
        }

        if (bn_down != null) {
            bn_down.setOnTouchListener((v,en)->{
                if (en.getAction()==MotionEvent.ACTION_DOWN) carManager.sendToCar(serverIP, serverPort, "s");
                else if (en.getAction()==MotionEvent.ACTION_UP) carManager.sendToCar(serverIP, serverPort, "0");
                return true;
            });
        }

        if (bn_right != null) {
            bn_right.setOnTouchListener((v,en)->{
                if (en.getAction()==MotionEvent.ACTION_DOWN) carManager.sendToCar(serverIP, serverPort, "d");
                else if (en.getAction()==MotionEvent.ACTION_UP) carManager.sendToCar(serverIP, serverPort, "0");
                return true;
            });
        }

        if (bu_left != null) {
            bu_left.setOnTouchListener((v,en)->{
                if (en.getAction()==MotionEvent.ACTION_DOWN) carManager.sendToCar(serverIP, serverPort, "a");
                else if (en.getAction()==MotionEvent.ACTION_UP) carManager.sendToCar(serverIP, serverPort, "0");
                return true;
            });
        }

        if (bu_Send != null) {
            bu_Send.setOnClickListener(v->{
                SeekBar sp_speedBar = findViewById(R.id.speedBar);
                TextView speedText = findViewById(R.id.textView);
                if(sp_speedBar != null){
                    int sp = sp_speedBar.getProgress();
                    if(speedText != null) speedText.setText("当前时速："+sp);
                    carManager.sendToCar(serverIP, serverPort, String.valueOf(sp));
                }
            });
        }

        if (btn_open_sound != null) {
            btn_open_sound.setOnClickListener(v->toggleAudioListen());
        }

        if (btnTalk != null) {
            btnTalk.setOnClickListener(v->toggleAudioTalk());
        }

        if (bu_lamp != null) {
            bu_lamp.setOnClickListener(v->control_lamp());
        }

        if (btn_navigate != null) {
            btn_navigate.setOnClickListener(v -> finish());
        }

        if (btn_alert_history != null) {
            btn_alert_history.setOnClickListener(v -> {
                Intent intent = new Intent(this, AlertHistoryActivity.class);
                startActivity(intent);
            });
        }

        if (btn_enable_detection != null) {
            btn_enable_detection.setOnClickListener(v ->
                    DetectionControlManager.startDetection(Thermal_imaging.this));
        }
    }

    /**
     * 申请录音和网络权限；录音权限用于对讲，网络权限用于访问摄像头和 RK3588。
     */
    private void initPermissions() {
        ActivityCompat.requestPermissions(this,
                new String[]{Manifest.permission.RECORD_AUDIO, Manifest.permission.INTERNET}, 100);
    }

    /**
     * 切换摄像头声音监听状态，并同步更新按钮图标。
     */
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

    /**
     * 切换手机到摄像头的对讲状态，并同步更新麦克风按钮图标。
     */
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

    /**
     * 切换摄像头补光灯状态，Control=1 打开，Control=0 关闭。
     */
    private void control_lamp() {
        isLampOpen = !isLampOpen;
        if (isLampOpen) {
            cameraManager.lightControl(NetworkConfig.getLightUrl(cameraIP), 1);
            bu_lamp.setImageResource(R.drawable.lamp_open);
        } else {
            cameraManager.lightControl(NetworkConfig.getLightUrl(cameraIP), 0);
            bu_lamp.setImageResource(R.drawable.lamp_off);
        }
    }
}
