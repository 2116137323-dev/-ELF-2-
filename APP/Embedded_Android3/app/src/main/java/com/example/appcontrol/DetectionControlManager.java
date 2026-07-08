package com.example.appcontrol;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.widget.Toast;

import java.io.IOException;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.FormBody;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

/**
 * 检测开关控制工具类。
 *
 * Android 端点击“开启检测”后，会调用 RK3588 端 Flask 服务的 /detection/start 接口。
 * RK3588 收到请求后才开始双路识别，避免设备启动后立即自动报警。
 */
final class DetectionControlManager {
    // OkHttpClient 可复用连接池和线程池，作为静态单例避免每次点击都创建新客户端。
    private static final OkHttpClient CLIENT = new OkHttpClient();

    // 网络回调运行在 OkHttp 后台线程，Toast 必须切回主线程显示。
    private static final Handler MAIN_HANDLER = new Handler(Looper.getMainLooper());

    // 工具类不需要实例化。
    private DetectionControlManager() {}

    /**
     * 请求 RK3588 后端开启目标检测。
     *
     * 返回 200：检测已启动。
     * 返回 409：后端仍在等待当前报警确认，此时不允许继续开启新一轮检测。
     */
    static void startDetection(Context context) {
        String url = NetworkConfig.getDetectionStartUrl(NetworkConfig.SERVER_IP);
        RequestBody body = new FormBody.Builder().build();
        Request req = new Request.Builder().url(url).post(body).build();
        CLIENT.newCall(req).enqueue(new Callback() {
            @Override
            public void onFailure(Call call, IOException e) {
                showToast(context, "开启检测失败");
            }

            @Override
            public void onResponse(Call call, Response response) throws IOException {
                String msg;
                if (response.isSuccessful()) {
                    msg = "已开启检测";
                } else if (response.code() == 409) {
                    msg = "请先确认当前报警";
                } else {
                    msg = "开启检测失败";
                }
                response.close();
                showToast(context, msg);
            }
        });
    }

    /**
     * 在主线程弹出 Toast，使用 applicationContext 避免 Activity 短时间内销毁导致引用问题。
     */
    private static void showToast(Context context, String message) {
        MAIN_HANDLER.post(() ->
                Toast.makeText(context.getApplicationContext(), message, Toast.LENGTH_SHORT).show());
    }
}
