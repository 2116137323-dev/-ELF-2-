package com.example.appcontrol;

import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.text.TextUtils;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

public class LoginActivity extends AppCompatActivity {

    private Button bu_Login;
    private EditText et_Account, et_Password, et_CameraIp;

    private String name = "admin";
    private String pass = "admin";

    // 默认的摄像头 IP
    private String defaultCameraIp = "192.168.72.123";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_login);

        bu_Login = findViewById(R.id.Login);
        et_Account = findViewById(R.id.Account);
        et_Password = findViewById(R.id.Password);
        // 绑定 IP 输入框控件
        et_CameraIp = findViewById(R.id.CameraIp);

        // 设置输入框默认显示的 IP
        if (et_CameraIp != null) {
            et_CameraIp.setText(defaultCameraIp);
        }

        bu_Login.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                String account = et_Account.getText().toString();
                String password = et_Password.getText().toString();

                // 获取用户在界面上输入的 IP
                String inputIp = "";
                if (et_CameraIp != null) {
                    inputIp = et_CameraIp.getText().toString().trim();
                }

                // 简单的非空校验
                if (TextUtils.isEmpty(inputIp)) {
                    Toast.makeText(LoginActivity.this, "请输入摄像头IP", Toast.LENGTH_SHORT).show();
                    return;
                }

                final String finalIp = inputIp; // 供内部类使用

                if (TextUtils.equals(account, name)) {
                    if (TextUtils.equals(password, pass)) {
                        Toast.makeText(LoginActivity.this, "登录成功", Toast.LENGTH_LONG).show();
                        // 延迟 1 秒后跳转到主页面，不阻塞 UI 线程
                        new Handler().postDelayed(new Runnable() {
                            @Override
                            public void run() {
                                main(finalIp); // 将获取到的 IP 传给跳转方法
                            }
                        }, 1000);
                    } else {
                        Toast.makeText(LoginActivity.this, "密码错误", Toast.LENGTH_LONG).show();
                    }
                } else {
                    Toast.makeText(LoginActivity.this, "账号错误", Toast.LENGTH_LONG).show();
                }
            }
        });
    }

    // 接收 IP 并通过 Intent 传给 MainActivity
    void main(String cameraIp) {
        Intent intent = new Intent(LoginActivity.this, MainActivity.class);
        intent.putExtra("CAMERA_IP", cameraIp); // 打包 IP 数据
        startActivity(intent);
        finish(); // 登录后关闭登录页面
    }
}