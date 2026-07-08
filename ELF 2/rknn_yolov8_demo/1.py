# 模块文档字符串：概述双路检测服务的职责与能力
"""
双路(可见光 + 热成像)采集、RKNN 推理、联动报警与上报服务。
"""

import os  # 导入 os 模块，用于环境变量与目录操作

# OpenCV 通过 FFmpeg 拉取 RTSP 时的低延迟参数：走 TCP，尽量减少缓冲与分析时长
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|analyzeduration;500000"  # 设置 FFmpeg RTSP 低延迟捕获选项
import sys  # 导入 sys 模块，用于解释器与路径相关操作
import time  # 导入 time 模块，用于时间戳与延时
import threading  # 导入 threading 模块，用于多线程采集/推理/渲染
import serial  # 导入 pyserial，用于热成像串口通信
import cv2  # 导入 OpenCV，用于图像采集、处理与编码
import numpy as np  # 导入 NumPy，用于数组与矩阵运算
import requests  # 导入 requests，用于 HTTP 上报安卓端
from rknnlite.api import RKNNLite  # 从 rknnlite 导入 RKNN Lite 推理 API
from flask import Flask, Response, request  # 导入 Flask 组件，用于 Web 推流与 REST API
import camera_digest_alarm  # 导入摄像头摘要鉴权报警模块
from detection_marker_bridge import (  # 导入独立 ROS2/RViz 标注桥接模块
    enqueue_detection_marker,
    publish_emergency_stop,
    start_ros2_marker_bridge,
)

# ==================== 1. 硬件配置 ====================
# 热成像串口配置(厂商协议：每帧 1544 字节；温度点阵 32x24，共 768 点)
PORT, BAUD = "/dev/ttyDevice2", 460800  # 热成像串口设备路径与通信波特率
W, H, FRAME_SIZE = 32, 24, 1544  # 温度矩阵宽度、高度及单帧字节长度

# RKNN 模型路径(热成像/可见光各一套)
THERMAL_MODEL = 'model/yolov8_fp7.rknn'  # 热成像 YOLOv8 RKNN 模型文件路径
CAMERA_MODEL = 'model/yolov8_fp8.rknn'  # 可见光 YOLOv8 RKNN 模型文件路径

# 可见光摄像头 RTSP 拉流地址与 HTTP 控制参数(用于触发摄像头语音报警)
RTSP_URL = "rtsp://admin:123456@192.168.72.153:554/ch01.264"  # 可见光 RTSP 视频流地址
CAMERA_HTTP_HOST = "192.168.72.153:80"  # 摄像头 HTTP 控制主机地址
CAMERA_HTTP_USER = "admin"  # 摄像头 HTTP 鉴权用户名
CAMERA_HTTP_PASS = "123456"  # 摄像头 HTTP 鉴权密码
CAMERA_ALARM_SOUND_ID = 1  # 触发报警时播放的音频文件 ID
CAMERA_ALARM_CH = 1  # 报警音频输出通道号
CAMERA_ALARM_DEV = 1  # 报警音频设备编号

# 推理/后处理参数
OBJ_THRESH = 0.50  # 默认目标检测置信度阈值
NMS_THRESH = 0.25  # 非极大值抑制 IoU 阈值
BOX_HOLD_SEC = 1  # 检测框在画面上保留显示的时长(秒)
IMG_SIZE = (640, 640)  # 模型推理与 Web 推流的统一输入尺寸

# 类别映射与独立阈值
THERMAL_CLASS_THRESHOLDS = {0: 0.05}  # 热成像各类别对应的置信度阈值
CAMERA_CLASS_LABELS = {0: "PERSON", 1: "AMPUTATED_LIMB"}  # 可见光类别 ID 到名称的映射
CAMERA_CLASS_THRESHOLDS = {0: OBJ_THRESH, 1: 0.34}  # 可见光各类别独立置信度阈值
CAMERA_CLASS_IDS = {"PERSON": 0, "AMPUTATED_LIMB": 1}  # 可见光类别名称到 ID 的反向映射

# 上报/联动参数
ANDROID_URL = "http://192.168.72.158:8080/upload"  # 安卓端事件图片与状态上报 URL
SAVE_DIR = "captured_events"  # 报警事件截图本地保存目录名
COOLDOWN = 1.0  # 两次报警触发之间的冷却时间(秒)
SUSPECT_NO_VITAL_VERIFY_SEC = 0.2  # 无生命体征嫌疑状态的确认等待时长
AMPUTATED_LIMB_VERIFY_SEC = 0.2  # 残肢检测状态的确认等待时长
STREAM_FPS = 15  # MJPEG Web 推流目标帧率
STREAM_JPEG_QUALITY = 75  # MJPEG 推流 JPEG 压缩质量(0-100)
THERMAL_FLIP_HORIZONTAL = True  # 热成像渲染时是否水平翻转画面

# 纯温度判定“有热源”的门槛(用于热成像模型检出不稳定时的兜底)
THERMAL_HOT_TEMP_C = 29.5  # 判定为热点的最低温度(摄氏度)
THERMAL_HOT_PIXEL_COUNT = 4  # 超过温度门槛的像素个数阈值
THERMAL_DISPLAY_TEMP_OFFSET = 5.5  # 热成像显示温度的偏移校正值
THERMAL_DISPLAY_MIN_C = 10.0  # 热成像伪彩色显示的温度下限
THERMAL_DISPLAY_BG_PERCENTILE = 60  # 背景温度估计所用的百分位
THERMAL_DISPLAY_MIN_DELTA_C = 1.2  # 相对背景的最小温升，用于触发高亮显示
THERMAL_DISPLAY_CONTRAST_C = 6.0  # 伪彩色映射的对比度温度范围
THERMAL_DISPLAY_BASE_DELTA_C = 1.0  # 归一化显示时的基础温升
THERMAL_MIN_SPAN_C = 9.0  # 热成像渲染所需的最小温度跨度
THERMAL_CLAHE_CLIP = 2.5  # CLAHE 对比度限制的 clip 值
THERMAL_CLAHE_GRID = (8, 8)  # CLAHE 分块网格尺寸(列, 行)

# 仅上传可见光单图的状态
SINGLE_IMAGE_STATUSES = frozenset({  # 仅需上传可见光单张截图的报警状态集合
    "suspect_no_vital", "camera_detected", "amputated_limb_no_temperature",  # 三种单图上报状态名
})  # 结束 frozenset 字面量

# 后处理与热成像渲染复用对象，避免每帧重复创建
_BOX_PROCESS_CACHE = {}  # 检测框后处理缓存，按输入 shape 复用中间结果
_THERMAL_CLAHE = cv2.createCLAHE(  # 全局 CLAHE 对象，用于热成像对比度增强
    clipLimit=THERMAL_CLAHE_CLIP, tileGridSize=THERMAL_CLAHE_GRID  # 使用上方配置的 clip 与网格参数
)  # 结束 createCLAHE 调用

if not os.path.exists(SAVE_DIR):  # 若事件截图保存目录尚不存在
    os.makedirs(SAVE_DIR)  # 创建本地保存目录

# ==================== 2. 全局状态 ====================
# state 用于多线程之间的数据交换：采集线程写入 raw_*，推理线程写入 *_boxes 与 *_detect_time，渲染线程写入 *_frame
app = Flask(__name__)  # 创建 Flask 应用实例，供 Web 推流与 API 使用
lock = threading.Lock()  # 全局互斥锁，保护 state 字典的并发读写
state = {  # 多线程共享的全局状态字典
    'raw_thermal': None,  # 24x32 温度矩阵(float, 摄氏度)
    'raw_thermal_seq': 0,  # 热成像最新帧序号，用于新帧触发推理
    'raw_camera': None,  # 可见光原始帧(BGR)
    'raw_camera_seq': 0,  # 可见光最新帧序号，用于新帧触发推理
    'infer_thermal_frame': None,  # 热成像识别输入帧(640x640，与 Web 推流画面一致)
    'infer_camera_frame': None,  # 可见光识别输入帧(640x640 BGR)
    'thermal_frame': np.zeros((480, 640, 3), dtype=np.uint8),  # 热成像显示帧(BGR，供 MJPEG 推流)
    'camera_frame': np.zeros((480, 640, 3), dtype=np.uint8),  # 可见光显示帧(BGR，供 MJPEG 推流)
    'thermal_frame_seq': 0,  # 热成像显示帧更新序号
    'camera_frame_seq': 0,  # 可见光显示帧更新序号
    'cam_boxes': None,  # 可见光目标框(基于 640x640 输入坐标)
    'cam_class_ids': None,  # 可见光目标类别
    'cam_detect_time': 0.0,  # 可见光最新检出时间戳
    'therm_boxes': None,  # 热成像人体框(基于 640x640 输入坐标)
    'therm_detect_time': 0.0,  # 热成像最新检出时间戳
    'mode': "SEARCH",  # 状态机：SEARCH / VERIFY / VERIFY_AMPUTATED_LIMB / COOLDOWN
    'last_trigger': 0,  # 上次触发报警的时间戳
    'detection_enabled': False,  # 手动检测开关：设备启动默认不检测，需安卓端手动开启
    'awaiting_ack': False,  # 上报后等待安卓端确认期间暂停识别
    'pending_timestamp': None,  # 当前等待确认的报警时间戳
    'running': True  # 全局退出标志
}  # 结束全局 state 字典


def reset_detection_results():  # 定义清空推理结果缓存的函数
    """清空推理结果缓存，供状态切换或报警后复用。"""  # 函数文档：重置检测缓存
    state['cam_boxes'] = None  # 清空可见光检测框
    state['cam_class_ids'] = None  # 清空可见光类别 ID
    state['therm_boxes'] = None  # 清空热成像检测框
    state['cam_detect_time'] = 0.0  # 重置可见光检测耗时
    state['therm_detect_time'] = 0.0  # 重置热成像检测耗时


def scale_box_to_display(box, flip_horizontal=False):  # 定义将推理框映射到显示坐标的函数
    """将 640x640 推理坐标映射到 640x480 显示坐标。"""  # 函数文档：坐标缩放与可选水平翻转
    x1, y1, x2, y2 = box.astype(int)  # 将框坐标转为整数
    x1d, y1d = max(0, x1), max(0, int(y1 * 0.75))  # Y 轴按 0.75 缩放到 480 高度
    x2d, y2d = min(640, int(x2)), min(480, int(y2 * 0.75))  # 裁剪到显示区域边界
    if flip_horizontal:  # 若需要水平镜像（热成像）
        x1d, x2d = 640 - x2d, 640 - x1d  # 对 X 坐标做左右翻转
    return x1d, y1d, x2d, y2d  # 返回显示用的 xyxy 坐标


# ==================== 3. NPU 初始化与后处理 ====================  # 模块分隔：NPU 初始化与 YOLO 后处理
def init_npus():  # 定义初始化双路 RKNN NPU 的函数
    """初始化两路 RKNN 并分别绑定到 RK3588 不同 NPU 核心，避免互相抢占。"""  # 函数文档：双 NPU 核心分配
    print("--> 初始化热成像 RKNN NPU (核心1)...")  # 打印热成像 NPU 初始化日志
    rknn_therm = RKNNLite()  # 创建热成像 RKNN 实例
    if (rknn_therm.load_rknn(THERMAL_MODEL) != 0 or  # 加载热成像 RKNN 模型失败
            rknn_therm.init_runtime(core_mask=RKNNLite.NPU_CORE_1) != 0):  # 或绑定 NPU 核心 1 失败
        print("热成像模型加载失败")  # 打印失败信息
        return None, None  # 返回空元组表示初始化失败

    print("--> 初始化可见光 RKNN NPU (核心2)...")  # 打印可见光 NPU 初始化日志
    rknn_cam = RKNNLite()  # 创建可见光 RKNN 实例
    if (rknn_cam.load_rknn(CAMERA_MODEL) != 0 or  # 加载可见光 RKNN 模型失败
            rknn_cam.init_runtime(core_mask=RKNNLite.NPU_CORE_2) != 0):  # 或绑定 NPU 核心 2 失败
        print("摄像头模型加载失败")  # 打印失败信息
        return None, None  # 返回空表示失败
    return rknn_therm, rknn_cam  # 返回两个已初始化的 RKNN 实例


def dfl(position):  # 定义 YOLOv8 DFL 分布焦点损失解码函数
    """YOLOv8 DFL(Distribution Focal Loss) 解码，将离散分布还原为连续偏移。"""  # 函数文档：DFL 解码
    n, c, h, w = position.shape  # 获取批次、通道、高、宽维度
    p_num = 4  # 每条边使用 4 个分布（左、上、右、下）
    mc = c // p_num  # 每条边的分布 bin 数量
    y = position.reshape(n, p_num, mc, h, w)  # 重塑为 (N,4,mc,H,W)
    e_y = np.exp(y - np.max(y, axis=2, keepdims=True))  # 数值稳定的 softmax 分子
    y = e_y / np.sum(e_y, axis=2, keepdims=True)  # 沿 bin 维归一化得到概率
    acc_metrix = np.arange(mc, dtype=np.float32).reshape(1, 1, mc, 1, 1)  # 构建 bin 索引权重
    y = np.sum(y * acc_metrix, axis=2)  # 加权求和得到连续偏移期望值
    return y  # 返回解码后的 4 通道偏移


def box_process(position):  # 定义将回归输出转为 xyxy 框的函数
    """将网络输出的回归分支还原为输入尺寸(640x640)上的 xyxy 绝对坐标。"""  # 函数文档：框坐标解码
    grid_h, grid_w = position.shape[2:4]  # 从张量形状取特征图高宽
    cache_key = (grid_h, grid_w)  # 用网格尺寸作为缓存键
    if cache_key not in _BOX_PROCESS_CACHE:  # 若该尺度网格尚未缓存
        col, row = np.meshgrid(np.arange(0, grid_w), np.arange(0, grid_h))  # 生成列行网格坐标
        col = col.reshape(1, 1, grid_h, grid_w)  # 重塑列网格为 4D
        row = row.reshape(1, 1, grid_h, grid_w)  # 重塑行网格为 4D
        grid = np.concatenate((col, row), axis=1)  # 拼接为 (1,2,H,W) 中心网格
        stride = np.array([IMG_SIZE[1] // grid_h, IMG_SIZE[0] // grid_w]).reshape(1, 2, 1, 1)  # 计算步长
        _BOX_PROCESS_CACHE[cache_key] = (grid, stride)  # 写入全局缓存
    grid, stride = _BOX_PROCESS_CACHE[cache_key]  # 从缓存读取网格与步长
    position = dfl(position)  # 对回归分支做 DFL 解码
    box_xy = grid + 0.5 - position[:, 0:2, :, :]  # 左上角 = 网格中心减左、上偏移
    box_xy2 = grid + 0.5 + position[:, 2:4, :, :]  # 右下角 = 网格中心加右、下偏移
    xyxy = np.concatenate((box_xy * stride, box_xy2 * stride), axis=1)  # 乘步长并拼接为 xyxy
    return xyxy  # 返回绝对像素坐标框


def nms_boxes(boxes, scores):  # 定义非极大值抑制函数
    """非极大值抑制：对同一类别的重叠框去重。"""  # 函数文档：NMS 去重
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]  # 分解框四边坐标
    areas = (x2 - x1) * (y2 - y1)  # 计算各框面积
    order = scores.argsort()[::-1]  # 按得分降序排列索引
    keep = []  # 保留框索引列表
    while order.size > 0:  # 仍有待处理框时循环
        i = order[0]  # 取当前最高分框
        keep.append(i)  # 加入保留列表
        xx1 = np.maximum(x1[i], x1[order[1:]])  # 与其余框求交叠区域左边界
        yy1 = np.maximum(y1[i], y1[order[1:]])  # 交叠区域上边界
        xx2 = np.minimum(x2[i], x2[order[1:]])  # 交叠区域右边界
        yy2 = np.minimum(y2[i], y2[order[1:]])  # 交叠区域下边界
        w = np.maximum(0.0, xx2 - xx1)  # 交叠宽度（非负）
        h = np.maximum(0.0, yy2 - yy1)  # 交叠高度（非负）
        inter = w * h  # 交叠面积
        ovr = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)  # 计算 IoU
        inds = np.where(ovr <= NMS_THRESH)[0]  # 找出 IoU 低于阈值的索引
        order = order[inds + 1]  # 更新待处理队列（跳过被抑制的框）
    return np.array(keep)  # 返回保留框的索引数组


def post_process(input_data, target_class_ids=None, class_thresholds=None):  # 定义 YOLOv8 完整后处理函数
    """YOLOv8 后处理：解码多尺度输出 + 置信度过滤(支持按类别阈值) + NMS。"""  # 函数文档：多尺度后处理流程
    boxes, classes_conf = [], []  # 初始化框列表与类别置信度列表
    for i in range(3):  # 遍历三个检测尺度
        boxes.append(box_process(input_data[i * 3]))  # 解码第 i 尺度的框回归输出
        classes_conf.append(input_data[i * 3 + 1])  # 收集对应尺度的类别置信度

    def sp_flatten(_in):  # 定义将特征图展平为 (N,C) 的内部函数
        ch = _in.shape[1]  # 获取通道数
        _in = _in.transpose(0, 2, 3, 1)  # 调整为 NHWC 布局
        return _in.reshape(-1, ch)  # 展平空间维，保留通道维

    boxes = np.concatenate([sp_flatten(_v) for _v in boxes])  # 合并三尺度所有框
    classes_conf = np.concatenate([sp_flatten(_v) for _v in classes_conf])  # 合并三尺度类别分数
    class_num = classes_conf.shape[1]  # 获取类别总数
    if target_class_ids is None:  # 若未指定目标类别
        target_class_ids = list(range(class_num))  # 默认检测全部类别

    valid_class_ids = [cid for cid in target_class_ids if 0 <= cid < class_num]  # 过滤合法类别 ID
    if not valid_class_ids:  # 若无有效类别
        return None, None, None  # 返回空三元组

    selected_scores = classes_conf[:, valid_class_ids]  # 只取目标类别的分数子矩阵
    best_pos = np.argmax(selected_scores, axis=1)  # 每个锚点在其目标类中的最佳位置
    best_scores = selected_scores[np.arange(selected_scores.shape[0]), best_pos]  # 对应最高分数
    best_class_ids = np.array(valid_class_ids, dtype=np.int32)[best_pos]  # 映射回全局类别 ID

    thresholds = np.array(  # 为每个检测实例构建置信度阈值数组
        [class_thresholds.get(int(class_id), OBJ_THRESH) if class_thresholds else OBJ_THRESH  # 优先类别阈值，否则全局
         for class_id in best_class_ids], dtype=np.float32)  # 按 best_class_ids 逐类取阈值

    keep_mask = best_scores >= thresholds  # 得分达到阈值的掩码
    if not np.any(keep_mask):  # 若全部被过滤
        return None, None, None  # 无有效检测

    boxes = boxes[keep_mask]  # 保留通过阈值的框
    best_scores = best_scores[keep_mask]  # 保留对应分数
    best_class_ids = best_class_ids[keep_mask]  # 保留对应类别

    kept_boxes, kept_scores, kept_class_ids = [], [], []  # 按类 NMS 后的结果容器
    for class_id in np.unique(best_class_ids):  # 对每个出现过的类别分别 NMS
        cls_mask = best_class_ids == class_id  # 当前类别的掩码
        cls_boxes = boxes[cls_mask]  # 该类所有框
        cls_scores = best_scores[cls_mask]  # 该类所有分数
        keep = nms_boxes(cls_boxes, cls_scores)  # 执行 NMS 得保留索引
        if len(keep) == 0:  # 若 NMS 后无框
            continue  # 跳过该类别
        kept_boxes.append(cls_boxes[keep])  # 追加保留框
        kept_scores.append(cls_scores[keep])  # 追加保留分数
        kept_class_ids.append(np.full(len(keep), class_id, dtype=np.int32))  # 填充类别 ID

    if not kept_boxes:  # 若所有类 NMS 后均为空
        return None, None, None  # 返回空

    boxes = np.concatenate(kept_boxes, axis=0)  # 合并各类保留框
    scores = np.concatenate(kept_scores, axis=0)  # 合并各类分数
    class_ids = np.concatenate(kept_class_ids, axis=0)  # 合并各类 ID
    order = np.argsort(scores)[::-1]  # 按分数降序排序索引
    return boxes[order], scores[order], class_ids[order]  # 返回排序后的框、分数、类别


def thermal_has_heat_signature(img_therm):  # 定义基于温度矩阵判定是否有热源的函数
    """仅基于温度矩阵做热源判定：最高温度与热点像素数同时达标才算“有热”。"""  # 函数文档：热源双条件判定
    if img_therm is None:  # 若无热成像数据
        return False, 0.0, 0  # 返回无热、零温度、零热点像素
    max_temp = float(np.max(img_therm))  # 计算全图最高温度
    hot_mask = img_therm >= THERMAL_HOT_TEMP_C  # 超过热点温度阈值的掩码
    hot_pixels = int(np.count_nonzero(hot_mask))  # 统计热点像素数量
    has_heat = max_temp >= THERMAL_HOT_TEMP_C and hot_pixels >= THERMAL_HOT_PIXEL_COUNT  # 温度与像素数均达标
    return has_heat, max_temp, hot_pixels  # 返回判定结果及统计量


def normalize_thermal_gray(img_therm):  # 定义将温度矩阵归一化为灰度图的函数
    """把 24x32 温度矩阵映射为对人体更友好的灰度图，兼顾背景层次与热点对比。"""  # 函数文档：热图灰度归一化
    temp = np.asarray(img_therm, dtype=np.float32)  # 转为 float32 数组
    if temp.size == 0:  # 若数组为空
        return np.zeros((H, W), dtype=np.uint8)  # 返回全零灰度图

    finite_mask = np.isfinite(temp)  # 标记有限数值（非 NaN/Inf）
    if not np.any(finite_mask):  # 若全部为无效值
        return np.zeros((temp.shape[0], temp.shape[1]), dtype=np.uint8)  # 返回同尺寸零图

    valid = temp[finite_mask]  # 提取有效温度值
    temp = temp.copy()  # 复制数组避免修改原数据
    temp[~finite_mask] = float(np.median(valid))  # 无效点用有效值中位数填充

    # 原始热阵列只有 24x32，先做轻微平滑，减少传感器毛刺点。
    temp = cv2.GaussianBlur(temp, (3, 3), 0)  # 3x3 高斯模糊降噪

    p5, p50, p95 = np.percentile(valid, [5, 50, 95])  # 计算 5/50/95 分位温度
    t_min = min(p5, p50 - THERMAL_MIN_SPAN_C * 0.5)  # 动态下限，保证最小跨度
    t_max = max(p95, p50 + THERMAL_MIN_SPAN_C * 0.5)  # 动态上限

    if (t_max - t_min) < THERMAL_MIN_SPAN_C:  # 若温度跨度仍过窄
        center = (t_min + t_max) * 0.5  # 取区间中心
        t_min = center - THERMAL_MIN_SPAN_C * 0.5  # 以中心扩展下限
        t_max = center + THERMAL_MIN_SPAN_C * 0.5  # 以中心扩展上限

    gray = np.clip((temp - t_min) * (255.0 / (t_max - t_min)), 0, 255).astype(np.uint8)  # 线性映射到 0-255
    return gray  # 返回 uint8 灰度图


def build_thermal_web_infer_frame(img_therm, infer_size=IMG_SIZE):  # 定义构建热成像推理帧的函数
    """热成像直接从渲染帧识别，直接生成模型输入尺寸。"""  # 函数文档：帧转推理输入
    if img_therm is None:  # 若无热图
        return np.zeros((infer_size[1], infer_size[0], 3), dtype=np.uint8)  # 返回黑色 BGR 占位图

    return render_thermal_display_frame(img_therm, infer_size)  # 直接从热成像帧生成模型输入，避免中间缩放


def render_thermal_frame(img_therm, size):  # 定义渲染热成像伪彩图的函数
    """生成更利于观察和识别的热成像伪彩图。"""  # 函数文档：伪彩热图渲染
    if img_therm is None:  # 若无输入热图
        return np.zeros((size[1], size[0], 3), dtype=np.uint8)  # 返回黑色 BGR 图

    gray = normalize_thermal_gray(img_therm)  # 先归一化为灰度
    interp = cv2.INTER_CUBIC if size[0] >= gray.shape[1] and size[1] >= gray.shape[0] else cv2.INTER_AREA  # 放大用三次插值，缩小用区域插值
    gray_large = cv2.resize(gray, size, interpolation=interp)  # 缩放到目标尺寸

    gray_large = _THERMAL_CLAHE.apply(gray_large)  # CLAHE 增强局部对比度

    blur = cv2.GaussianBlur(gray_large, (0, 0), 1.0)  # 轻微高斯模糊
    gray_large = cv2.addWeighted(gray_large, 1.20, blur, -0.20, 0)  # 锐化：原图减模糊
    return cv2.applyColorMap(gray_large, cv2.COLORMAP_JET)  # 应用 JET 伪彩色并返回


def render_thermal_display_frame(img_therm, size):  # 定义 Web 显示用热成像帧的函数
    """显示画面使用更稳定的热成像风格，避免空场噪声被拉成假热点。"""  # 函数文档：稳定显示渲染
    if img_therm is None:  # 若无热图数据
        return np.zeros((size[1], size[0], 3), dtype=np.uint8)  # 返回黑色占位图

    temp = np.asarray(img_therm, dtype=np.float32) + THERMAL_DISPLAY_TEMP_OFFSET  # 加显示温度偏移
    finite_mask = np.isfinite(temp)  # 有效温度掩码
    if not np.any(finite_mask):  # 无有效温度
        return np.zeros((size[1], size[0], 3), dtype=np.uint8)  # 返回零图

    temp = temp.copy()  # 复制以免修改原数组
    temp[~finite_mask] = float(np.median(temp[finite_mask]))  # 无效点用中位数填充
    temp = cv2.GaussianBlur(temp, (3, 3), 0)  # 平滑减少噪声

    valid = temp[temp >= THERMAL_DISPLAY_MIN_C]  # 高于显示最低温的有效像素
    if valid.size == 0:  # 若无达标像素
        return np.zeros((size[1], size[0], 3), dtype=np.uint8)  # 返回零图

    background_temp = max(  # 计算背景参考温度
        THERMAL_DISPLAY_MIN_C,  # 不低于显示最低温
        float(np.percentile(valid, THERMAL_DISPLAY_BG_PERCENTILE))  # 有效像素分位数作为背景
    )  # max 调用结束，得到背景参考温度
    temp_delta = temp - background_temp  # 相对背景的温度差
    gray = np.zeros(temp.shape, dtype=np.uint8)  # 初始化灰度图
    valid_mask = temp >= THERMAL_DISPLAY_MIN_C  # 可显示区域掩码
    gray[valid_mask] = np.clip(  # 仅对有效区域映射灰度
        (temp_delta[valid_mask] + THERMAL_DISPLAY_BASE_DELTA_C) *  # 加基线偏移后
        (255.0 / THERMAL_DISPLAY_CONTRAST_C),  # 按对比度缩放
        0,  # 下限 0
        255  # 上限 255
    ).astype(np.uint8)  # 转为 uint8

    interp = cv2.INTER_CUBIC if size[0] >= gray.shape[1] and size[1] >= gray.shape[0] else cv2.INTER_AREA  # 选择插值方式
    gray_large = cv2.resize(gray, size, interpolation=interp)  # 灰度图放大到显示尺寸
    mask_large = cv2.resize(valid_mask.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST) > 0  # 有效区域掩码同步缩放
    color_large = cv2.applyColorMap(gray_large, cv2.COLORMAP_JET)  # 伪彩色映射
    color_large[~mask_large] = 0  # 无效区域置黑
    if THERMAL_FLIP_HORIZONTAL:  # 若配置水平翻转
        color_large = cv2.flip(color_large, 1)  # 沿垂直轴镜像
    return color_large  # 返回 BGR 显示帧


def thermal_capture(ser_port):  # 定义热成像串口采集线程函数
    """热成像采集线程：解析 0x5A 帧头的 1544 字节串口帧，重建 24x32 温度矩阵。"""  # 函数文档：串口热图采集
    buffer = bytearray()  # 串口接收缓冲区
    print("--> 热成像采集线程已启动")  # 打印线程启动日志
    while state['running']:  # 服务运行期间循环采集
        try:  # 捕获串口读写异常
            if not ser_port:  # 若串口未打开
                time.sleep(0.1)  # 短暂等待后重试
                continue  # 跳过本轮
            if ser_port.in_waiting > 0:  # 若接收缓冲区有数据
                buffer.extend(ser_port.read(ser_port.in_waiting))  # 读入全部待读字节
                if len(buffer) > FRAME_SIZE * 2:  # 缓冲区过大时
                    buffer = buffer[-FRAME_SIZE * 2:]  # 只保留最近两帧长度

            # 串口协议：Byte0 为 0x5A 帧头；Byte4~1539 为 768 个点的 uint16 温度(= (T+40)*100)
            idx = buffer.find(0x5A)  # 查找帧头 0x5A 位置
            if idx != -1:  # 找到帧头
                if idx > 0:  # 帧头前有无效数据
                    del buffer[:idx]  # 丢弃帧头之前的内容
                if len(buffer) < FRAME_SIZE:  # 数据不足一整帧
                    continue  # 等待更多数据
                frame = buffer[:FRAME_SIZE]  # 截取一完整帧
                del buffer[:FRAME_SIZE]  # 从缓冲区移除已处理帧

                # 厂商解码公式：T = raw/100 - 40
                raw = np.frombuffer(frame, dtype=np.uint8, offset=4, count=1536).view(np.uint16)  # 解析 uint16 原始温度
                img = (raw.reshape(H, W) / 100.0) - 40.0  # 转为摄氏度并 reshape 为 HxW

                with lock:  # 加锁更新全局状态
                    state['raw_thermal'] = img  # 写入最新温度矩阵
                    state['raw_thermal_seq'] += 1  # 帧序号递增
            else:  # 未找到帧头
                if len(buffer) > 4096:  # 缓冲区异常膨胀
                    buffer.clear()  # 清空防止内存堆积
        except Exception as e:  # 采集过程异常
            print(f"热成像串口采集异常: {e}")  # 打印错误
            time.sleep(0.1)  # 异常后短暂休眠


def camera_capture():  # 定义可见光 RTSP 采集线程函数
    """可见光采集线程：OpenCV 拉取 RTSP，失败时释放句柄并重连。"""  # 函数文档：摄像头采集与重连
    print("--> 摄像头采集线程已启动")  # 打印启动日志
    cap = None  # VideoCapture 句柄，初始为空
    fail_count = 0  # 连续读帧失败计数
    while state['running']:  # 服务运行期间循环
        try:  # 捕获 OpenCV 异常
            if cap is None or not cap.isOpened():  # 若未连接或已断开
                time.sleep(1)  # 重连前等待 1 秒
                try:  # 尝试打开 RTSP
                    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)  # 使用 FFMPEG 后端打开流
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    fail_count = 0  # 重连成功后重置连续失败计数
                except Exception:  # 捕获打开摄像头过程中的任意异常
                    cap = None  # 打开失败时将捕获对象置空
                continue  # 跳过本次循环剩余逻辑，等待下次重试

            ret, frame = cap.read()  # 从摄像头读取一帧，ret 表示是否成功
            if ret:  # 读取成功时更新共享状态
                with lock:  # 加锁保护全局 state 的并发写入
                    state['raw_camera'] = frame  # 保存最新原始可见光帧
                    state['raw_camera_seq'] += 1  # 递增帧序号供推理线程检测新帧
                fail_count = 0  # 读取成功则清零失败计数
            else:  # 读取失败时累计失败次数
                fail_count += 1  # 连续读帧失败计数加一
                if fail_count >= 20:  # 连续失败达到阈值则尝试重连
                    try:  # 尝试释放当前 VideoCapture 资源
                        cap.release()  # 释放摄像头句柄
                    except Exception:  # 释放过程异常时忽略
                        pass  # 继续执行后续清理逻辑
                    cap = None  # 置空以触发下一轮重连
                    fail_count = 0  # 重置失败计数
                time.sleep(0.005)  # 短暂休眠避免空转占满 CPU
        except Exception as e:  # 捕获采集循环中的未预期异常
            print(f"摄像头采集异常: {e}")  # 打印异常信息便于排查
            if cap is not None:  # 若摄像头对象仍存在则尝试释放
                try:  # 安全释放摄像头
                    cap.release()  # 释放 VideoCapture
                except Exception:  # 释放失败时忽略
                    pass  # 继续清理状态
            cap = None  # 异常后将 cap 置空以便重连
            time.sleep(0.5)  # 异常后等待较长时间再重试


# ==================== 5. NPU 推理线程 ====================  # 模块分隔：NPU 推理相关线程
def camera_infer_thread(rknn_cam):  # 可见光摄像头 RKNN 推理线程入口
    """可见光推理线程：预处理 + RKNN 推理 + 后处理，更新 cam_boxes/cam_class_ids。"""  # 函数文档说明
    print("--> 可见光 NPU 推理线程已启动 (Core 2)")  # 启动日志
    last_seq = -1  # 记录已处理过的 raw_camera 帧序号
    while state['running']:  # 主循环：服务运行期间持续推理
        with lock:  # 加锁读取共享状态
            if state['awaiting_ack'] or not state['detection_enabled']:  # 等待确认或检测关闭时不取帧
                img_cam = None  # 标记无可用输入
            elif state['raw_camera'] is None or state['raw_camera_seq'] == last_seq:  # 无新帧
                img_cam = None  # 跳过重复或空帧
            else:  # 存在未处理的新帧
                raw_seq = state['raw_camera_seq']  # 记录当前帧序号
                img_cam = state['raw_camera'].copy()  # 拷贝帧避免推理时被采集线程覆盖

        if img_cam is None:  # 无输入时短暂休眠
            time.sleep(0.02 if state['awaiting_ack'] or not state['detection_enabled'] else 0.005)  # 等待确认时休眠更久
            continue  # 进入下一轮循环

        try:  # 推理过程异常保护
            cam_resized = cv2.resize(img_cam, IMG_SIZE)  # 缩放到模型输入尺寸
            cam_rgb = cv2.cvtColor(cam_resized, cv2.COLOR_BGR2RGB)  # BGR 转 RGB 供 RKNN 使用
            out = rknn_cam.inference(inputs=[np.expand_dims(cam_rgb, axis=0)])  # NPU 执行可见光推理
            cam_boxes, _, cam_class_ids = post_process(  # 后处理得到检测框与类别
                out,  # 模型原始输出
                target_class_ids=[0, 1],  # 可见光目标类别：人与截肢
                class_thresholds=CAMERA_CLASS_THRESHOLDS  # 各类别置信度阈值
            )  # post_process 调用结束
            last_seq = raw_seq  # 标记该帧已处理
            with lock:  # 加锁写回推理结果
                state['infer_camera_frame'] = cam_resized  # 保存推理用缩放帧供上报
                state['cam_boxes'] = cam_boxes  # 更新可见光检测框
                state['cam_class_ids'] = cam_class_ids  # 更新可见光类别 ID
                if cam_boxes is not None:  # 有有效检测时
                    state['cam_detect_time'] = time.time()  # 记录检测时间用于框保持
        except Exception as e:  # 推理异常捕获
            print(f"摄像头推理异常: {e}")  # 打印错误信息


def thermal_infer_thread(rknn_therm):  # 热成像 RKNN 推理线程入口
    """热成像推理线程：使用与 Web 推流一致的显示画面作为 YOLO 输入。"""  # 函数文档说明
    print("--> 热成像 NPU 推理线程已启动 (Core 1)")  # 启动日志
    last_seq = -1  # 记录已处理过的 raw_thermal 帧序号
    while state['running']:  # 主循环：服务运行期间持续推理
        with lock:  # 加锁读取共享状态
            if state['awaiting_ack'] or not state['detection_enabled']:  # 等待确认或检测关闭时不取帧
                img_therm = None  # 标记无可用输入
            elif state['raw_thermal'] is None or state['raw_thermal_seq'] == last_seq:  # 无新帧
                img_therm = None  # 跳过重复或空帧
            else:  # 存在未处理的新帧
                raw_seq = state['raw_thermal_seq']  # 记录当前帧序号
                img_therm = state['raw_thermal'].copy()  # 拷贝帧避免推理时被覆盖

        if img_therm is None:  # 无输入时短暂休眠
            time.sleep(0.02 if state['awaiting_ack'] or not state['detection_enabled'] else 0.005)  # 等待确认时休眠更久
            continue  # 进入下一轮循环

        try:  # 推理过程异常保护
            color_therm = build_thermal_web_infer_frame(img_therm, IMG_SIZE)  # 构建与 Web 一致的热成像推理帧
            t_rgb = cv2.cvtColor(color_therm, cv2.COLOR_BGR2RGB)  # BGR 转 RGB 供 RKNN 使用

            out_t = rknn_therm.inference(inputs=[np.expand_dims(t_rgb, axis=0)])  # NPU 执行热成像推理
            therm_boxes, _, _ = post_process(  # 后处理得到热成像检测框
                out_t,  # 模型原始输出
                target_class_ids=[0],  # 热成像仅检测人体类别
                class_thresholds=THERMAL_CLASS_THRESHOLDS  # 热成像类别阈值
            )  # post_process 调用结束
            last_seq = raw_seq  # 标记该帧已处理
            with lock:  # 加锁写回推理结果
                state['infer_thermal_frame'] = color_therm  # 保存推理用帧供上报
                state['therm_boxes'] = therm_boxes  # 更新热成像检测框
                if therm_boxes is not None:  # 有有效检测时
                    state['therm_detect_time'] = time.time()  # 记录检测时间用于框保持
        except Exception as e:  # 推理异常捕获
            print(f"热成像推理异常: {e}")  # 打印错误信息


def logic_and_render_thread():  # 主控逻辑与画面渲染线程入口
    """主控线程：基于数据流检测结果触发上报，不依赖 Web 推流。"""  # 函数文档说明
    verify_start_time = 0.0  # 进入复核状态时记录起始时间
    last_camera_seq = -1  # 上次已渲染的可见光帧序号
    last_thermal_seq = -1  # 上次已渲染的热成像帧序号
    camera_base = np.zeros((480, 640, 3), dtype=np.uint8)  # 可见光显示底图缓存
    thermal_base = np.zeros((480, 640, 3), dtype=np.uint8)  # 热成像显示底图缓存
    print("--> 逻辑控制线程已启动")  # 启动日志

    while state['running']:  # 主循环：持续渲染并驱动状态机
        now = time.time()  # 当前时间戳，用于框保持与超时判定
        img_therm = None  # 本轮热成像原始帧引用

        with lock:  # 加锁批量读取共享状态
            thermal_seq = state['raw_thermal_seq']  # 热成像原始帧序号
            camera_seq = state['raw_camera_seq']  # 可见光原始帧序号
            if state['raw_thermal'] is not None:  # 若有热成像原始数据
                img_therm = state['raw_thermal']  # 引用热成像帧（不拷贝以减开销）
            raw_camera = state['raw_camera']  # 可见光原始帧引用
            c_boxes = state['cam_boxes']  # 可见光检测框
            c_ids = state['cam_class_ids']  # 可见光检测类别
            c_time = state['cam_detect_time']  # 可见光最近检测时间
            t_boxes = state['therm_boxes']  # 热成像检测框
            t_time = state['therm_detect_time']  # 热成像最近检测时间
            mode = state['mode']  # 当前状态机模式
            detection_enabled = state['detection_enabled']  # 检测是否启用
            awaiting_ack = state['awaiting_ack']  # 是否等待安卓端确认

        if raw_camera is not None and camera_seq != last_camera_seq:  # 可见光有更新
            camera_base = cv2.resize(raw_camera, (640, 480))  # 缩放为显示尺寸并缓存
            last_camera_seq = camera_seq  # 更新已处理序号
        disp_cam = camera_base.copy()  # 拷贝底图用于绘制检测框

        if img_therm is not None and thermal_seq != last_thermal_seq:  # 热成像有更新
            thermal_base = render_thermal_display_frame(img_therm, (640, 480))  # 渲染伪彩色显示帧
            last_thermal_seq = thermal_seq  # 更新已处理序号
        disp_therm = thermal_base.copy()  # 拷贝底图用于绘制检测框

        if c_boxes is not None and c_ids is not None and now - c_time <= BOX_HOLD_SEC:  # 可见光框仍在保持期内
            for box, class_id in zip(c_boxes, c_ids):  # 遍历每个检测框及类别
                x1d, y1d, x2d, y2d = scale_box_to_display(box)  # 将模型坐标映射到显示尺寸
                cv2.rectangle(disp_cam, (x1d, y1d), (x2d, y2d), (0, 0, 255), 2)  # 绘制红色矩形框
                label = CAMERA_CLASS_LABELS.get(int(class_id), f"CLASS_{int(class_id)}")  # 获取类别中文/英文标签
                cv2.putText(disp_cam, label, (x1d, max(20, y1d - 10)),  # 在框上方绘制类别文字
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)  # 字体、字号与颜色

        if t_boxes is not None and now - t_time <= BOX_HOLD_SEC:  # 热成像框仍在保持期内
            for box in t_boxes:  # 遍历热成像检测框
                # 推理输入已与 Web 推流画面一致(含水平翻转)，无需再次翻转坐标  # 坐标已与显示对齐
                x1d, y1d, x2d, y2d = scale_box_to_display(box)  # 映射到显示坐标
                cv2.rectangle(disp_therm, (x1d, y1d), (x2d, y2d), (0, 255, 0), 2)  # 绘制绿色矩形框
                cv2.putText(disp_therm, "THERMAL", (x1d, max(20, y1d - 10)),  # 绘制 THERMAL 标签
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)  # 字体、字号与颜色

        if awaiting_ack or not detection_enabled:  # 等待确认或检测关闭时仅更新画面
            with lock:  # 加锁写回推流帧
                state['thermal_frame'] = disp_therm  # 更新热成像推流帧
                state['camera_frame'] = disp_cam  # 更新可见光推流帧
                state['thermal_frame_seq'] += 1  # 递增热成像推流序号
                state['camera_frame_seq'] += 1  # 递增可见光推流序号
            time.sleep(0.02)  # 降低 CPU 占用
            continue  # 跳过状态机逻辑

        # 状态机判定  # 根据双路检测结果驱动报警与模式切换
        cam_active = c_boxes is not None and now - c_time <= BOX_HOLD_SEC  # 可见光检测是否在有效期内
        therm_active = t_boxes is not None and now - t_time <= BOX_HOLD_SEC  # 热成像 YOLO 检测是否有效
        thermal_heat_active, thermal_max_temp, thermal_hot_pixels = thermal_has_heat_signature(  # 分析热成像体温特征
            img_therm)  # 传入原始热成像帧
        therm_person_or_heat_active = therm_active or thermal_heat_active  # 热成像人体或高温任一成立

        amputated_limb_active = (  # 是否检测到截肢类别
            cam_active and c_ids is not None and np.any(c_ids == CAMERA_CLASS_IDS["AMPUTATED_LIMB"])  # 可见光框有效且含截肢 ID
        )  # 截肢活跃判定表达式结束
        cam_person_active = (  # 是否检测到普通人体
            cam_active and c_ids is not None and np.any(c_ids == CAMERA_CLASS_IDS["PERSON"])  # 可见光框有效且含人体 ID
        )  # 人体活跃判定表达式结束

        next_mode = mode  # 默认保持当前模式

        if mode == "SEARCH":  # 搜索模式：等待目标出现
            if amputated_limb_active:  # 发现截肢目标
                print("--> [状态机] 发现 AMPUTATED_LIMB，拉起热成像复核")  # 日志
                next_mode = "VERIFY_AMPUTATED_LIMB"  # 进入截肢复核模式
                verify_start_time = now  # 记录复核开始时间
            elif cam_person_active:  # 发现普通人体
                if therm_person_or_heat_active:  # 热成像同时确认
                    print("--> [报警] 双路确认！")  # 双路确认日志
                    trigger_alarm("dual_detected", now)  # 触发双路检测报警
                    next_mode = "COOLDOWN"  # 进入冷却等待确认
                else:  # 热成像尚未确认
                    next_mode = "VERIFY"  # 进入普通复核模式
                    verify_start_time = now  # 记录复核开始时间

        elif mode == "VERIFY_AMPUTATED_LIMB":  # 截肢复核模式
            if amputated_limb_active and therm_person_or_heat_active:  # 截肢且检测到体温
                print(  # 打印报警日志（含最高温）
                    f"--> [报警] AMPUTATED_LIMB 且有体温 (max={thermal_max_temp:.1f}C)")  # 有体温报警
                trigger_alarm("amputated_limb_with_temperature", now)  # 触发有体温截肢报警
                next_mode = "COOLDOWN"  # 进入冷却
            elif amputated_limb_active and (  # 截肢但复核超时
                    now - verify_start_time >= AMPUTATED_LIMB_VERIFY_SEC):  # 超过截肢复核时限
                print(  # 打印无明显体温报警日志
                    f"--> [报警] AMPUTATED_LIMB 无明显体温 (max={thermal_max_temp:.1f}C)")  # 无体温报警
                trigger_alarm("amputated_limb_no_temperature", now)  # 触发无体温截肢报警
                next_mode = "COOLDOWN"  # 进入冷却
            elif not cam_active:  # 可见光目标消失
                next_mode = "SEARCH"  # 回到搜索模式

        elif mode == "VERIFY":  # 普通人体验证模式
            if amputated_limb_active:  # 复核期间升级为截肢
                next_mode = "VERIFY_AMPUTATED_LIMB"  # 切换至截肢复核
                verify_start_time = now  # 重置复核计时
            elif cam_person_active and therm_person_or_heat_active:  # 双路在复核期内确认
                print("--> [报警] 双路确认！")  # 双路确认日志
                trigger_alarm("dual_detected", now)  # 触发双路报警
                next_mode = "COOLDOWN"  # 进入冷却
            elif cam_person_active and (now - verify_start_time >= SUSPECT_NO_VITAL_VERIFY_SEC):  # 热成像超时未联动
                print("--> [报警] 摄像头先识别，0.2s 内热成像未联动，直接上报")  # 单路上报日志
                trigger_alarm("camera_detected", now)  # 触发仅可见光报警
                next_mode = "COOLDOWN"  # 进入冷却
            elif not cam_person_active:  # 人体目标消失
                next_mode = "SEARCH"  # 回到搜索

        elif mode == "COOLDOWN":  # 冷却模式：等待安卓确认
            with lock:  # 重新读取确认状态（可能已被 /ack 更新）
                awaiting_ack = state['awaiting_ack']  # 是否仍在等待确认
            if not awaiting_ack:  # 安卓已确认
                print("--> [状态机] 安卓已确认，恢复识别")  # 恢复日志
                next_mode = "SEARCH"  # 回到搜索模式

        with lock:  # 写回状态机结果与推流帧
            state['mode'] = next_mode  # 更新状态机模式
            state['thermal_frame'] = disp_therm  # 更新热成像推流帧
            state['camera_frame'] = disp_cam  # 更新可见光推流帧
            state['thermal_frame_seq'] += 1  # 递增热成像推流序号
            state['camera_frame_seq'] += 1  # 递增可见光推流序号

        time.sleep(0.01)  # 控制主控循环频率


def build_upload_frames():  # 构建上报用的可见光与热成像帧
    """从推理线程保存的识别输入帧生成上报图片，不叠加任何可视化。"""  # 函数文档说明
    with lock:  # 加锁读取推理帧与原始帧
        infer_cam = None if state['infer_camera_frame'] is None else state['infer_camera_frame'].copy()  # 拷贝可见光推理帧
        infer_therm = None if state['infer_thermal_frame'] is None else state['infer_thermal_frame'].copy()  # 拷贝热成像推理帧
        raw_cam = None if state['raw_camera'] is None else state['raw_camera'].copy()  # 拷贝可见光原始帧作兜底
        raw_therm = None if state['raw_thermal'] is None else state['raw_thermal'].copy()  # 拷贝热成像原始帧作兜底

    camera_frame = np.zeros((IMG_SIZE[1], IMG_SIZE[0], 3), dtype=np.uint8)  # 默认黑色可见光上报帧
    thermal_frame = np.zeros((IMG_SIZE[1], IMG_SIZE[0], 3), dtype=np.uint8)  # 默认黑色热成像上报帧

    if infer_cam is not None:  # 优先使用推理输入帧
        camera_frame = infer_cam  # 直接采用已缩放的推理帧
    elif raw_cam is not None:  # 推理帧不可用时用原始帧
        camera_frame = cv2.resize(raw_cam, IMG_SIZE)  # 缩放到模型尺寸

    if infer_therm is not None:  # 优先使用热成像推理帧
        thermal_frame = infer_therm  # 直接采用已处理的推理帧
    elif raw_therm is not None:  # 推理帧不可用时用原始帧
        thermal_frame = build_thermal_web_infer_frame(raw_therm, IMG_SIZE)  # 构建与 Web 一致的热成像帧

    return thermal_frame, camera_frame  # 返回热成像与可见光上报图像


def trigger_alarm(status, now):  # 触发报警并暂停检测直至安卓确认
    """触发报警：识别到立即上报；上报后暂停识别，等待安卓端确认后恢复。"""  # 函数文档说明
    with lock:  # 加锁修改全局报警状态
        if state['awaiting_ack']:  # 已在等待确认则忽略重复触发
            return  # 直接返回避免重复上报
        ts = time.strftime("%Y%m%d_%H%M%S")  # 生成时间戳字符串作为文件名前缀
        state['detection_enabled'] = False  # 暂停检测
        state['awaiting_ack'] = True  # 标记等待安卓确认
        state['pending_timestamp'] = ts  # 记录待确认的时间戳
        state['last_trigger'] = now  # 记录最近触发时间
        state['mode'] = "COOLDOWN"  # 状态机进入冷却模式
        reset_detection_results()  # 清空检测结果缓存

    enqueue_detection_marker(status, ts)  # 向 ROS2 发布检测标记
    frm_t, frm_c = build_upload_frames()  # 构建上报用双路图像

    threading.Thread(  # 异步线程执行保存与上传，避免阻塞主逻辑
        target=save_and_send,  # 目标函数
        args=(frm_t.copy(), frm_c.copy(), status, ts),  # 传入图像副本与状态信息
        daemon=True  # 守护线程随主进程退出
    ).start()  # 启动上传线程


def save_and_send(frm_t, frm_c, status, ts):  # 保存截图、触发语音报警并 HTTP 上传
    """保存截图 + 触发摄像头语音报警 + HTTP 上传(根据状态决定单图或双图)。"""  # 函数文档说明
    upload_ok = False  # 上传是否成功标志
    try:  # 整体流程异常保护
        p_t = os.path.join(SAVE_DIR, f"{ts}_thermal.jpg")  # 热成像本地保存路径
        p_c = os.path.join(SAVE_DIR, f"{ts}_camera.jpg")  # 可见光本地保存路径

        cv2.imwrite(p_c, frm_c)  # 写入可见光 JPEG
        if status not in SINGLE_IMAGE_STATUSES:  # 非单图状态需保存热成像
            cv2.imwrite(p_t, frm_t)  # 写入热成像 JPEG

        ok, msg = camera_digest_alarm.trigger_speech_alarm(  # 调用摄像头 HTTP 语音报警接口
            host=CAMERA_HTTP_HOST,  # 摄像头 IP/主机
            username=CAMERA_HTTP_USER,  # HTTP Digest 用户名
            password=CAMERA_HTTP_PASS,  # HTTP Digest 密码
            sound_id=CAMERA_ALARM_SOUND_ID,  # 报警音 ID
            ch=CAMERA_ALARM_CH,  # 报警通道
            dev=CAMERA_ALARM_DEV,  # 设备标识
            timeout=3.0,  # 请求超时秒数
        )  # trigger_speech_alarm 调用结束
        print(f"--> [摄像头报警] {'已触发' if ok else '触发失败'}: {msg}")  # 打印语音报警结果

        print(f"--> [上传] 正在发送至安卓端 {ANDROID_URL}")  # 上传开始日志
        if status in SINGLE_IMAGE_STATUSES:  # 仅需上传可见光的报警类型
            with open(p_c, 'rb') as f_c:  # 以二进制打开可见光图片
                res = requests.post(  # POST  multipart 上传
                    ANDROID_URL,  # 安卓端接收 URL
                    files={'camera': ('camera.jpg', f_c, 'image/jpeg')},  # 仅上传可见光文件
                    data={'timestamp': ts, 'status': status},  # 附带时间戳与状态
                    timeout=10.0  # HTTP 超时
                )  # 单图 requests.post 调用结束
        else:  # 双图上传
            with open(p_t, 'rb') as f_t, open(p_c, 'rb') as f_c:  # 同时打开热成像与可见光
                res = requests.post(  # POST  multipart 上传
                    ANDROID_URL,  # 安卓端接收 URL
                    files={'thermal': ('thermal.jpg', f_t, 'image/jpeg'),  # 热成像文件字段
                           'camera': ('camera.jpg', f_c, 'image/jpeg')},  # 可见光文件字段
                    data={'timestamp': ts, 'status': status},  # 附带时间戳与状态
                    timeout=10.0  # HTTP 超时
                )  # 双图 requests.post 调用结束
        print(f"--> [上传] 响应码: {res.status_code}")  # 打印 HTTP 响应码
        upload_ok = (res.status_code == 200)  # 200 视为上传成功
    except Exception as e:  # 捕获保存或上传异常
        print(f"上传异常: {e}")  # 打印异常信息
    finally:  # 无论成功失败均执行
        if not upload_ok:  # 上传失败时解除等待确认，允许重试
            with lock:  # 加锁恢复状态
                state['awaiting_ack'] = False  # 取消等待确认
                state['pending_timestamp'] = None  # 清空待确认时间戳


@app.route('/ack', methods=['POST'])  # 安卓端确认报警的路由
def ack():  # 处理 /ack POST 请求
    ts = request.values.get('timestamp')  # 读取客户端提交的时间戳（可选）
    with lock:  # 加锁更新确认状态
        if state['awaiting_ack'] and (ts is None or ts == state.get('pending_timestamp')):  # 时间戳匹配或未提供
            state['awaiting_ack'] = False  # 解除等待确认
            state['pending_timestamp'] = None  # 清空待确认时间戳
    return "OK"  # 返回成功响应


@app.route('/detection/start', methods=['POST'])  # 启动检测的路由
def detection_start():  # 处理 /detection/start POST 请求
    with lock:  # 加锁修改检测状态
        if state['awaiting_ack']:  # 仍在等待报警确认时不允许启动
            return "PENDING_ACK", 409  # 返回冲突状态码
        state['detection_enabled'] = True  # 启用检测
        state['mode'] = "SEARCH"  # 重置为搜索模式
        reset_detection_results()  # 清空历史检测结果
    # 重新开始检测时解除底盘急停，允许后续重新下发导航目标后行驶  # 业务说明
    publish_emergency_stop(False)  # 发布 ROS2 急停解除指令
    return "OK"  # 返回成功


@app.route('/detection/stop', methods=['POST'])  # 停止检测的路由
def detection_stop():  # 处理 /detection/stop POST 请求
    with lock:  # 加锁修改检测状态
        state['detection_enabled'] = False  # 关闭检测
        state['mode'] = "SEARCH"  # 重置为搜索模式
        reset_detection_results()  # 清空检测结果
    return "OK"  # 返回成功


def gen_video_stream(frame_key):  # MJPEG 视频流生成器
    """MJPEG 生成器：循环编码 JPEG 并按 multipart/x-mixed-replace 输出。"""  # 函数文档说明
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), STREAM_JPEG_QUALITY]  # JPEG 编码质量参数
    interval = 1.0 / max(1, int(STREAM_FPS))  # 每帧最小间隔（秒）
    seq_key = f"{frame_key}_seq"  # 对应帧序号在 state 中的键名
    last_seq = -1  # 上次已编码的帧序号
    last_ts = time.monotonic()  # 上次编码时刻（单调时钟）
    while True:  # 无限循环供 Flask Response 流式输出
        now = time.monotonic()  # 当前单调时钟
        dt = now - last_ts  # 距上次编码经过的时间
        if dt < interval:  # 未到下一帧时间点
            time.sleep(interval - dt)  # 休眠至间隔满足
        last_ts = time.monotonic()  # 更新上次编码时刻
        with lock:  # 加锁读取推流帧
            seq = state[seq_key]  # 当前帧序号
            if seq == last_seq:  # 帧未更新
                need_encode = False  # 跳过编码
            else:  # 有新帧
                f = state[frame_key].copy()  # 拷贝帧避免编码时被修改
                last_seq = seq  # 记录已处理序号
                need_encode = True  # 需要编码
        if not need_encode:  # 无新帧则继续等待
            continue  # 进入下一轮
        ok, jpg = cv2.imencode('.jpg', f, encode_params)  # 将 BGR 帧编码为 JPEG
        if not ok:  # 编码失败
            continue  # 跳过本帧
        yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpg.tobytes() + b'\r\n'  # 输出 MJPEG 分片


@app.route('/')  # 根路径：双画面预览页
def index():  # 返回 HTML 预览页面
    """简单的双画面预览页。"""  # 函数文档说明
    return """ <!DOCTYPE html> <html> <head><meta name="viewport" content="width=device-width, initial-scale=1.0"> <title>RK3588 Dual NPU</title> <style> body { background: #2c3e50; color: white; font-family: Arial; margin: 0; padding: 10px; text-align: center; } .container { display: flex; flex-wrap: wrap; gap: 15px; justify-content: center; } .video-box { flex: 1; min-width: 300px; max-width: 640px; position: relative; background: black; border: 3px solid #34495e; border-radius: 8px; overflow: hidden; aspect-ratio: 4/3; } .video-box img { width: 100%; height: 100%; object-fit: contain; display: block; } .label { position: absolute; top: 10px; left: 10px; background: rgba(0,0,0,0.6); padding: 4px 8px; border-radius: 4px; font-size: 12px; } </style> </head> <body> <h1>RK3588 NPU 双摄并行推理系统</h1> <div class="container"> <div class="video-box"><img src="/thermal_feed"><div class="label">热成像</div></div> <div class="video-box"><img src="/camera_feed"><div class="label">可见光</div></div> </div> </body></html> """  # 内联 HTML 页面字符串


@app.route('/thermal_feed')  # 热成像 MJPEG 流路由
def thermal_feed():  # 返回热成像视频流
    """热成像 MJPEG 推流。"""  # 函数文档说明
    return Response(gen_video_stream('thermal_frame'),  # 使用 thermal_frame 键生成流
                    mimetype='multipart/x-mixed-replace; boundary=frame')  # 设置 MJPEG MIME 类型


@app.route('/camera_feed')  # 可见光 MJPEG 流路由
def camera_feed():  # 返回可见光视频流
    """可见光 MJPEG 推流。"""  # 函数文档说明
    return Response(gen_video_stream('camera_frame'),  # 使用 camera_frame 键生成流
                    mimetype='multipart/x-mixed-replace; boundary=frame')  # 设置 MJPEG MIME 类型


if __name__ == '__main__':  # 脚本直接运行时进入主入口
    # 启动入口：初始化 NPU、打开串口、启动各线程，然后启动 Flask  # 主流程说明
    print("=" * 40)  # 打印分隔线
    print("  RK3588 NPU 双路并行推理系统")  # 打印系统标题
    print("=" * 40)  # 打印分隔线

    rknn_therm, rknn_cam = init_npus()  # 初始化热成像与可见光 RKNN 模型
    if not rknn_therm or not rknn_cam:  # 任一 NPU 初始化失败
        print("NPU 初始化失败！")  # 错误提示
        sys.exit(1)  # 非零退出码终止进程

    ser_obj = None  # 串口对象初始为空
    try:  # 尝试打开热成像串口
        print("--> 打开串口...")  # 日志
        ser_obj = serial.Serial(PORT, BAUD,  # 打开指定端口与波特率
                                timeout=0.01)  # 读超时 0.01 秒
        ser_obj.write(bytes([0x5A, 0x01, 0x01]))  # 发送热成像模块初始化命令
        print("--> 串口 OK")  # 成功日志
    except Exception as e:  # 串口打开失败
        print(f"串口初始化失败: {e}")  # 打印异常（热成像采集可能不可用）

    threading.Thread(target=thermal_capture, args=(ser_obj,),  # 启动热成像采集线程
                     daemon=True).start()  # 守护线程
    threading.Thread(target=camera_capture,  # 启动可见光采集线程
                     daemon=True).start()  # 守护线程
    threading.Thread(target=camera_infer_thread, args=(rknn_cam,),  # 启动可见光 NPU 推理线程
                     daemon=True).start()  # 守护线程
    threading.Thread(target=thermal_infer_thread, args=(rknn_therm,),  # 启动热成像 NPU 推理线程
                     daemon=True).start()  # 守护线程
    threading.Thread(target=logic_and_render_thread,  # 启动逻辑控制与渲染线程
                     daemon=True).start()  # 守护线程
    start_ros2_marker_bridge(lambda: state['running'])  # 启动 ROS2 检测标记桥接

    try:  # 启动 Flask Web 服务
        app.run(host='0.0.0.0', port=5001, threaded=True, debug=False,  # 监听所有网卡 5001 端口
                use_reloader=False)  # 禁用重载器（多线程环境）
    except KeyboardInterrupt:  # 用户 Ctrl+C 中断
        print("\n正在退出...")  # 退出提示
        state['running'] = False  # 通知各线程停止
        time.sleep(0.5)  # 等待线程收尾
        if ser_obj:  # 若串口已打开
            try:  # 尝试关闭串口
                ser_obj.close()  # 释放串口资源
            except Exception:  # 关闭失败时忽略
                pass  # 继续退出
