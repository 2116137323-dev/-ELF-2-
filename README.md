# 嵌入式大赛项目技术文档

## 一、项目简介

本项目由两部分组成：

1. **Android 上位机控制端**
   - 负责小车控制、摄像头控制、双向对讲、热成像预览、报警历史查看。
   - 通过局域网与底盘、摄像头和 RK3588 识别端通信。

2. **RK3588 端双路识别服务**
   - 对可见光和热成像进行并行采集与推理。
   - 检测到目标后生成报警事件、上传 Android 端，并在 ROS2 中发布定位标注。
   - 识别结果可通过 Web 页面实时预览。

---

## 二、项目目录结构

```text
新修改/
├─ README.md
├─ APP/
│  └─ Embedded_Android3/
│     └─ app/
│        └─ src/main/java/com/example/appcontrol/
│           ├─ MainActivity.java
│           ├─ LoginActivity.java
│           ├─ Thermal_imaging.java
│           ├─ AlertHistoryActivity.java
│           ├─ AlertServerService.java
│           ├─ AlertDialogManager.java
│           ├─ CarControlManager.java
│           ├─ CameraControlManager.java
│           ├─ IntercomManager.java
│           ├─ DetectionControlManager.java
│           └─ NetworkConfig.java
└─ ELF 2/
   ├─ rknn_yolov8_demo/
   │  ├─ 1.py
   │  ├─ camera_digest_alarm.py
   │  └─ detection_marker_bridge.py
   └─ elf_slam_ws/
      └─ src/elf_slam/elf_slam/
         ├─ diff_drive_controller.py
         ├─ encoder_bridge.py
         ├─ robot_description_publisher.py
         └─ scan_stamp_fix.py
```

---

## 三、系统总体流程

### 1. Android 端工作流程

- 用户在 `LoginActivity` 登录后进入主界面。
- `MainActivity` 负责：
  - 控制小车前进、后退、转向、调速；
  - 控制摄像头云台和补光灯；
  - 打开/关闭对讲监听与语音回传；
  - 打开热成像页面；
  - 查看报警历史；
  - 开启 RK3588 端识别服务。
- `Thermal_imaging` 页面负责：
  - 显示热成像 Web 预览；
  - 保持和 `MainActivity` 相同的网络配置；
  - 控制灯光、对讲、检测开关；
  - 接收报警广播并弹窗提示。
- `AlertServerService` 用于监听报警事件并向应用内广播。
- `AlertHistoryActivity` 用于查看报警图片历史。

### 2. RK3588 端工作流程

- `1.py` 启动后完成：
  - 热成像串口采集；
  - 可见光 RTSP 采集；
  - 双路 RKNN 推理；
  - 状态机联动报警；
  - 图片保存与上传；
  - ROS2 定位点标注；
  - Flask Web 预览。
- 检测到目标后会：
  - 保存报警图片；
  - 触发摄像头语音报警；
  - 上传图片和状态到 Android 端；
  - 在 ROS2 中生成地图定位点；
  - 必要时触发急停或取消导航。

---

## 四、Android 端模块说明

### 1. `MainActivity.java`

主控制页面，承担全局控制入口。

#### 主要功能

- 小车方向控制：`w/s/a/d/0`
- 小车调速
- 摄像头云台控制
- 补光灯控制
- 音频监听和对讲
- 跳转热成像页面
- 查看报警历史
- 启动检测
- 启动报警监听前台服务

#### 关键逻辑

- 通过 `NetworkConfig` 动态同步小车 IP 和摄像头 IP。
- `onResume()` 时重新启动视频播放，避免返回后黑屏。
- `onPause()` 时释放 VLC 资源，避免占用解码器和网络通道。
- 收到报警广播后调用 `AlertDialogManager.showAlertDialog()` 弹窗。

---

### 2. `Thermal_imaging.java`

热成像页面，主要用于热成像视频预览和相关控制。

#### 主要功能

- 通过 `WebView` 打开 RK3588 提供的热成像 Web 页面；
- 控制小车方向和灯光；
- 控制对讲；
- 开启检测；
- 查看报警历史；
- 接收报警广播。

#### 特点

- 页面中的 IP 地址可从 `MainActivity` 传入。
- `onStop()` 和 `onDestroy()` 中主动释放对讲、连接和广播注册，避免页面切换后资源占用。

---

### 3. `CarControlManager.java`

小车底盘控制类。

#### 主要功能

- 与小车控制端建立 TCP 连接；
- 发送方向与速度指令；
- 连接异常时自动重连；
- 退出页面时主动关闭连接。

#### 命令含义

- `w`：前进
- `s`：后退
- `a`：左转
- `d`：右转
- `0`：停止
- 数字字符串：速度值

---

### 4. `CameraControlManager.java`

摄像头 HTTP 控制类。

#### 主要功能

- 云台控制
- 补光灯控制
- 处理摄像头私有接口的认证

#### 鉴权说明

- 云台接口使用标准 HTTP Digest 鉴权；
- 补光灯接口使用摄像头固件自定义的 `X-Digest` 鉴权。

---

### 5. `IntercomManager.java`

摄像头对讲管理类。

#### 监听流程

- 通过 RTSP 建立音频拉流会话；
- 使用 RTP over TCP 接收摄像头音频；
- 将 G.711u 解码为 PCM；
- 通过 `AudioTrack` 播放。

#### 对讲流程

- 使用 `AudioRecord` 采集手机麦克风音频；
- 将 PCM 转换为 G.711u；
- 封装为 RTP 包；
- 通过 RTSP backchannel 回传到摄像头。

#### 关键处理

- 使用 `AcousticEchoCanceler` 降低回声；
- 使用 `NoiseSuppressor` 降噪；
- 使用锁保护录音和播放对象，避免关闭时并发崩溃。

---

### 6. `DetectionControlManager.java`

检测开关控制类。

#### 主要功能

- 点击“开启检测”后请求 RK3588 端的 `/detection/start`；
- 处理服务器返回状态；
- 在主线程显示 Toast。

#### 返回码说明

- `200`：检测已启动；
- `409`：当前仍有报警待确认，暂不允许启动检测。

---

### 7. `NetworkConfig.java`

网络配置中心。

#### 主要内容

- 默认服务器 IP
- 默认摄像头 IP
- RTSP 端口
- 热成像 Web 地址
- 各类接口 URL 生成函数

#### 作用

统一管理所有网络地址，避免在各个页面中硬编码。

---

### 8. `AlertHistoryActivity.java`

报警历史页面。

#### 主要功能

- 扫描本地报警图片；
- 按时间戳显示记录；
- 支持查看、确认、清空历史；
- 将图片列表渲染到 `ListView`。

#### 数据来源

报警事件由 RK3588 端上传后保存在 Android 私有目录中，历史页读取该目录下的图片进行展示。

---

### 9. `AlertDialogManager.java`

报警弹窗管理类。

#### 作用

- 在收到报警广播后弹出确认对话框；
- 提示报警时间、状态；
- 引导用户确认报警。

---

### 10. `AlertServerService.java`

报警监听前台服务。

#### 作用

- 保持应用在后台时仍能接收报警事件；
- 负责监听并向应用发送报警广播；
- 提高报警通知可靠性。

---

### 11. `LoginActivity.java`

登录页面。

#### 作用

- 作为应用入口；
- 收集或传入小车 IP、摄像头 IP；
- 进入 `MainActivity` 后完成网络配置同步。

---

## 五、RK3588 端模块说明

### 1. `1.py`

双路检测主程序。

#### 主要功能

- 热成像串口采集；
- 可见光 RTSP 采集；
- 双路 RKNN 推理；
- 状态机联动；
- 报警图片保存与上传；
- 触发摄像头语音报警；
- ROS2 定位点标注；
- Flask Web 视频预览；
- 安卓端确认接口 `/ack`；
- 检测开关接口 `/detection/start` 和 `/detection/stop`。

#### 状态机概念

程序使用状态机控制报警逻辑，主要状态包括：

- `SEARCH`：搜索目标；
- `VERIFY`：普通人体复核；
- `VERIFY_AMPUTATED_LIMB`：残肢复核；
- `COOLDOWN`：报警后等待确认。

#### 报警逻辑

- 可见光和热成像同时检测到目标时触发双路报警；
- 仅可见光检测到人体且热成像未联动时触发单路报警；
- 检测到残肢时走独立分支处理；
- 报警后暂停识别，等待 Android 端确认后恢复。

---

### 2. `camera_digest_alarm.py`

摄像头语音报警工具。

#### 作用

- 通过 Digest 鉴权登录摄像头接口；
- 调用语音报警接口触发指定音频播放；
- 为 `1.py` 的报警流程提供封装。

---

### 3. `detection_marker_bridge.py`

ROS2/RViz 标注桥接模块。

#### 作用

- 接收报警事件；
- 查询当前机器人位姿；
- 向 RViz 发布球体和文字标注；
- 发布 `PoseStamped` 定位点；
- 在报警触发时执行急停或取消导航。

---

## 六、SLAM 与底盘控制模块说明

### 1. `diff_drive_controller.py`

差速底盘控制节点。

#### 主要功能

- 订阅 `/cmd_vel`；
- 把连续速度转换为离散串口命令；
- 订阅 `/emergency_stop`；
- 收到急停后立即停车；
- 通过限频和死区减少底盘抖动。

#### 命令映射概念

- 线速度和角速度经过归一化后，决定是前进、后退、左转、右转还是停车；
- 控制板使用 ASCII 命令而不是直接速度值。

---

### 2. `encoder_bridge.py`

编码器桥接节点。

#### 作用

- 读取底盘编码器数据；
- 发布里程计相关信息；
- 供 SLAM 或导航系统使用。

---

### 3. `robot_description_publisher.py`

机器人模型描述发布节点。

#### 作用

- 发布机器人 URDF / 机器人描述信息；
- 供 RViz、TF 或机器人可视化使用。

---

### 4. `scan_stamp_fix.py`

激光扫描时间戳修正脚本。

#### 作用

- 修正扫描数据的时间戳；
- 提高 SLAM/导航中传感器同步的稳定性。

---

## 七、核心通信接口

### Android 与 RK3588 通信

- `http://<RK3588_IP>:5001/ack`
- `http://<RK3588_IP>:5001/detection/start`
- `http://<RK3588_IP>:5001/detection/stop`
- `http://<RK3588_IP>:5001/thermal_feed`
- `http://<RK3588_IP>:5001/camera_feed`

### Android 与摄像头通信

- 云台控制：`/digest/frmPTZControl`
- 补光灯控制：`/digest/frmIotLightCfg`
- 对讲：RTSP backchannel
- 监听：RTSP 音频流

### RK3588 与摄像头通信

- RTSP 取流
- HTTP Digest 语音报警
- HTTP 上传报警图片到 Android

### RK3588 与 ROS2 通信

- `/cmd_vel`
- `/emergency_stop`
- `/dual_detect_markers`
- `/dual_detect_pose`
- `/visualization_marker`
- `/visualization_marker_array`

---

## 八、运行逻辑摘要

### Android 端

1. 启动应用并登录；
2. 进入主界面；
3. 控制小车和摄像头；
4. 打开热成像页面；
5. 点击开启检测。

### RK3588 端

1. 启动串口、RTSP、RKNN、Flask、ROS2；
2. 采集热成像和可见光；
3. 执行双路识别；
4. 命中报警条件后保存图片并上传；
5. Android 弹窗确认后恢复识别。

---

## 九、适合写进答辩或说明书的项目亮点

- 双路视觉融合识别：可见光 + 热成像联动；
- 报警后自动联动摄像头语音提示；
- Android 端统一控制小车、云台、灯光、对讲；
- ROS2 中实时生成报警定位标注；
- 支持热成像网页预览与历史报警管理；
- 识别后自动停止导航，增强安全性。

---

## 十、补充说明

当前 README 侧重项目总体技术文档和目录说明，适合作为答辩、验收和二次开发说明基础文档。

如果你愿意，我下一步可以继续帮你补：

- `README.md` 的“安装部署说明”
- “运行步骤”
- “接口说明表格”
- “硬件接线说明”
- “答辩用项目简介版”
