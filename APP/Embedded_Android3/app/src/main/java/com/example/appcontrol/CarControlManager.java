package com.example.appcontrol;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;

/**
 * 小车底盘 TCP 控制管理类。
 *
 * 负责与小车控制端建立 Socket 连接，并把界面按钮产生的控制字符发送给底盘。
 * 典型命令：w/s/a/d 表示前进/后退/左转/右转，0 表示停止，数字字符串表示速度。
 */
public class CarControlManager {
    // 所有 Socket 读写和关闭都用同一把锁保护，避免多个按钮快速点击时并发操作连接。
    private final Object lock = new Object();
    private Socket carSocket;
    private OutputStream carOutputStream;

    /**
     * 异步预连接小车控制端，避免在 UI 线程执行网络操作导致界面卡顿。
     */
    public void initConnection(String ip, int port) {
        new Thread(() -> {
            synchronized (lock) {
                try {
                    if (carSocket == null || carSocket.isClosed()) {
                        ensureConnected(ip, port);
                    }
                } catch (Exception e) {
                    e.printStackTrace();
                }
            }
        }).start();
    }

    /**
     * 向小车发送控制指令；若连接不存在或已断开，会先自动重连。
     */
    public void sendToCar(String ip, int port, String msg) {
        new Thread(() -> {
            synchronized (lock) {
                try {
                    if (carSocket == null || carSocket.isClosed() || carOutputStream == null) {
                        ensureConnected(ip, port);
                    }
                    if (carOutputStream != null) {
                        carOutputStream.write(msg.getBytes());
                        carOutputStream.flush();
                    }
                } catch (Exception e) {
                    e.printStackTrace();
                    closeConnectionInternal();
                }
            }
        }).start();
    }

    /**
     * 重新建立 Socket 连接。
     *
     * 每次重连前先关闭旧连接，避免旧输出流占用系统资源或继续写入失效连接。
     */
    private void ensureConnected(String ip, int port) throws Exception {
        closeConnectionInternal();
        Socket socket = new Socket();
        socket.connect(new InetSocketAddress(ip, port), 3000);
        carSocket = socket;
        carOutputStream = socket.getOutputStream();
    }

    /**
     * 主动关闭小车连接，通常在页面退出或 Activity 停止时调用。
     */
    public void closeConnection() {
        synchronized (lock) {
            closeConnectionInternal();
        }
    }

    /**
     * 内部关闭逻辑；调用方需要保证已持有 lock，防止关闭时另一个线程正在写入。
     */
    private void closeConnectionInternal() {
        try {
            if (carOutputStream != null) carOutputStream.close();
        } catch (Exception ignored) {
        }
        try {
            if (carSocket != null) carSocket.close();
        } catch (Exception ignored) {
        }
        carOutputStream = null;
        carSocket = null;
    }
}
