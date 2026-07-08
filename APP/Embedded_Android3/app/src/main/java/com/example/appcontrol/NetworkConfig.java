package com.example.appcontrol;

/**
 * 全局网络配置。
 *
 * 该类集中管理 Android 端需要访问的 RK3588 服务地址、摄像头地址、RTSP 端口和各接口路径。
 * 页面之间传入新的 IP 后，通过 updateIps() 更新静态变量，后续所有 URL 生成函数都会使用最新 IP。
 */
public class NetworkConfig {
    // RK3588/小车控制端 IP：既用于 TCP 小车控制，也用于 Flask 热成像与报警接口。
    public static String SERVER_IP = "192.168.72.163";

    // 小车 TCP 控制端口。
    public static int SERVER_PORT = 8080;

    // 可见光摄像头 IP，用于 RTSP 视频、对讲、云台和补光灯控制。
    public static String CAMERA_IP = "192.168.72.123";

    // 摄像头 RTSP 默认端口。
    public static final int RTSP_PORT = 554;

    // 热成像发布网页地址（固定）。
    public static final String THERMAL_WEB_URL = "http://192.168.72.163:5001";

    // 摄像头音频监听 RTSP 路径；同时也是可见光主码流路径。
    public static final String PATH_AUDIO_IN = "/ch01.264";

    // 摄像头回传对讲路径，使用 G.711u 编码。
    public static final String PATH_AUDIO_OUT = "/audioback/ch_00/type_g711u";

    /**
     * 根据入口页面传入的 IP 更新全局配置；空字符串表示保持默认值。
     */
    public static void updateIps(String carIp, String camIp) {
        if (carIp != null && !carIp.isEmpty()) SERVER_IP = carIp;
        if (camIp != null && !camIp.isEmpty()) CAMERA_IP = camIp;
    }

    /**
     * 生成带用户名密码的摄像头 RTSP 视频地址。
     */
    public static String getVideoUrl(String ip) {
        return "rtsp://admin:123456@" + ip + ":" + RTSP_PORT + PATH_AUDIO_IN;
    }

    /**
     * 摄像头云台控制接口地址。
     */
    public static String getPtzUrl(String ip) {
        return "http://" + ip + "/digest/frmPTZControl";
    }

    /**
     * 摄像头补光灯控制接口地址。
     */
    public static String getLightUrl(String ip) {
        return "http://" + ip + "/digest/frmIotLightCfg";
    }

    /**
     * RK3588 Flask 热成像/可见光双画面网页地址。
     */
    public static String getThermalWebUrl(String ip) {
        return "http://" + ip + ":5001";
    }

    /**
     * 报警确认接口地址，Android 确认后通知后端恢复检测。
     */
    public static String getAckUrl(String ip) {
        return "http://" + ip + ":5001/ack";
    }

    /**
     * 开启检测接口地址。
     */
    public static String getDetectionStartUrl(String ip) {
        return "http://" + ip + ":5001/detection/start";
    }

    /**
     * 停止检测接口地址。
     */
    public static String getDetectionStopUrl(String ip) {
        return "http://" + ip + ":5001/detection/stop";
    }
}
