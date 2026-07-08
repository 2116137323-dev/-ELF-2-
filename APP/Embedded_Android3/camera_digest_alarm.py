
import os
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|analyzeduration;500000"
import sys
import time
import threading
import serial
import cv2
import numpy as np
import requests
from rknnlite.api import RKNNLite
from flask import Flask, Response
import camera_digest_alarm

# ==================== 1. 硬件配置 ====================
# 串口
PORT, BAUD = "/dev/ttyUSB1", 460800
W, H, FRAME_SIZE = 32, 24, 1544
TEMP_OFFSET = 5.5

# 模型路径
THERMAL_MODEL = 'model/yolov8_fp2.rknn'
CAMERA_MODEL = 'model/yolov8_fp3.rknn'

# 摄像头 RTSP
RTSP_URL = "rtsp://admin:123456@192.168.72.182/:554/ch01_sub.264"
CAMERA_HTTP_HOST = "192.168.72.182:80"
CAMERA_HTTP_USER = "admin"
CAMERA_HTTP_PASS = "123456"
CAMERA_ALARM_SOUND_ID = 1
CAMERA_ALARM_CH = 1
CAMERA_ALARM_DEV = 1

# NPU & 推理配置
OBJ_THRESH = 0.25  # 降低识别阈值，更容易框出目标
NMS_THRESH = 0.45
CAMERA_INFER_INTERVAL = 2
THERMAL_INFER_INTERVAL_IDLE = 6
THERMAL_INFER_INTERVAL_VERIFY = 2
BOX_HOLD_SEC = 0.6
IMG_SIZE = (640, 640)

# 联动配置
ANDROID_URL = "http://192.168.72.158:8080/upload"
SAVE_DIR = "captured_events"
COOLDOWN = 8.0
SUSPECT_NO_VITAL_VERIFY_SEC = 2.5

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# ==================== 2. 全局状态锁 ====================
app = Flask(__name__)
lock = threading.Lock()
state = {
    'thermal_frame': np.zeros((480, 640, 3), dtype=np.uint8),
    'camera_frame': np.zeros((480, 640, 3), dtype=np.uint8),
    'raw_thermal': None,
    'raw_camera': None,
    'last_trigger': 0,
    'running': True
}

# ==================== 3. NPU 初始化与后处理 ====================
def init_npus():
    print("--> 初始化热成像 RKNN NPU (核心1)...")
    rknn_therm = RKNNLite()
    if rknn_therm.load_rknn(THERMAL_MODEL) != 0 or \
       rknn_therm.init_runtime(core_mask=RKNNLite.NPU_CORE_1) != 0:
        print("热成像模型加载失败")
        return None, None

    print("--> 初始化可见光 RKNN NPU (核心2)...")
    rknn_cam = RKNNLite()
    if rknn_cam.load_rknn(CAMERA_MODEL) != 0 or \
       rknn_cam.init_runtime(core_mask=RKNNLite.NPU_CORE_2) != 0:
        print("摄像头模型加载失败")
        return None, None
    return rknn_therm, rknn_cam

def dfl(position):
    n, c, h, w = position.shape
    p_num = 4
    mc = c // p_num
    y = position.reshape(n, p_num, mc, h, w)
    e_y = np.exp(y - np.max(y, axis=2, keepdims=True))
    y = e_y / np.sum(e_y, axis=2, keepdims=True)
    acc_metrix = np.arange(mc, dtype=np.float32).reshape(1, 1, mc, 1, 1)
    y = np.sum(y * acc_metrix, axis=2)
    return y

def box_process(position):
    grid_h, grid_w = position.shape[2:4]
    col, row = np.meshgrid(np.arange(0, grid_w), np.arange(0, grid_h))
    col = col.reshape(1, 1, grid_h, grid_w)
    row = row.reshape(1, 1, grid_h, grid_w)
    grid = np.concatenate((col, row), axis=1)
    stride = np.array([IMG_SIZE[1] // grid_h, IMG_SIZE[0] // grid_w]).reshape(1, 2, 1, 1)
    position = dfl(position)
    box_xy = grid + 0.5 - position[:, 0:2, :, :]
    box_xy2 = grid + 0.5 + position[:, 2:4, :, :]
    xyxy = np.concatenate((box_xy * stride, box_xy2 * stride), axis=1)
    return xyxy

def nms_boxes(boxes, scores):
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        ovr = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
        inds = np.where(ovr <= NMS_THRESH)[0]
        order = order[inds + 1]
    return np.array(keep)

def post_process(input_data):
    boxes, classes_conf = [], []
    for i in range(3):
        boxes.append(box_process(input_data[i * 3]))
        classes_conf.append(input_data[i * 3 + 1])
    
    def sp_flatten(_in):
        ch = _in.shape[1]
        _in = _in.transpose(0, 2, 3, 1)
        return _in.reshape(-1, ch)
    
    boxes = np.concatenate([sp_flatten(_v) for _v in boxes])
    classes_conf = np.concatenate([sp_flatten(_v) for _v in classes_conf])
    class_num = classes_conf.shape[1]
    
    if class_num == 1:
        person_scores = classes_conf[:, 0].flatten()
    elif class_num == 2:
        person_scores = classes_conf[:, 1].flatten()
    else:
        person_scores = classes_conf[:, 0].flatten()
    
    _class_pos = np.where(person_scores >= OBJ_THRESH)[0]
    if len(_class_pos) == 0: return None, None
    
    boxes = boxes[_class_pos]
    person_scores = person_scores[_class_pos]
    keep = nms_boxes(boxes, person_scores)
    
    if len(keep) == 0: return None, None
    return boxes[keep], person_scores[keep]

# ==================== 4. 数据采集线程 ====================
def thermal_capture(ser_port):
    buffer = bytearray()
    print("--> 热成像采集线程已启动")
    while state['running']:
        try:
            if not ser_port:
                time.sleep(0.1)
                continue
            if ser_port.in_waiting > 0:
                buffer.extend(ser_port.read(ser_port.in_waiting))
                if len(buffer) > FRAME_SIZE * 2:
                    buffer = buffer[-FRAME_SIZE * 2:]
            
            idx = buffer.find(0x5A)
            if idx != -1:
                if idx > 0: del buffer[:idx]
                if len(buffer) < FRAME_SIZE: continue
                frame = buffer[:FRAME_SIZE]
                del buffer[:FRAME_SIZE]
                
                raw = np.frombuffer(frame, dtype=np.uint8, offset=4, count=1536).view(np.uint16)
                img = (raw.reshape(H, W) / 100.0) - 40.0 + TEMP_OFFSET
                
                with lock:
                    state['raw_thermal'] = img
            else:
                if len(buffer) > 4096: buffer.clear()
        except Exception as e:
            print(f"热成像异常: {e}")
            time.sleep(0.1)

def camera_capture():
    print("--> 摄像头采集线程已启动")
    cap = None
    fail_count = 0
    while state['running']:
        try:
            if cap is None or not cap.isOpened():
                time.sleep(1)
                try:
                    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    fail_count = 0
                except Exception:
                    cap = None
                continue

            ret, frame = cap.read()

            if ret:
                with lock:
                    state['raw_camera'] = frame
                fail_count = 0
            else:
                fail_count += 1
                if fail_count >= 20:
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = None
                    fail_count = 0
                time.sleep(0.005)
        except Exception as e:
            print(f"摄像头异常: {e}")
            if cap is not None:
                try: cap.release()
                except: pass
            cap = None
            time.sleep(0.5)

# ==================== 5. NPU 主推理循环 ====================
def main_loop(rknn_therm, rknn_cam):
    frame_count = 0
    mode = "SEARCH"
    last_cam_boxes = None
    last_therm_boxes = None
    last_cam_detect_time = 0.0
    last_therm_detect_time = 0.0
    verify_start_time = 0.0
    print("--> NPU 推理主循环已启动")
    while state['running']:
        frame_count += 1
        
        # 1. 获取数据
        img_therm = None
        img_cam = None
        with lock:
            if state['raw_thermal'] is not None:
                img_therm = state['raw_thermal'].copy()
            if state['raw_camera'] is not None:
                img_cam = state['raw_camera'].copy()
        
        # 2. 先做画面基础渲染
        disp_therm = np.zeros((480, 640, 3), dtype=np.uint8)
        disp_cam = np.zeros((480, 640, 3), dtype=np.uint8)
        
        if img_cam is not None:
            disp_cam = cv2.resize(img_cam, (640, 480))
        
        if img_therm is not None:
            t_min, t_max = 28.0, 35.0
            t_norm = np.clip((img_therm - t_min) * (255.0 / (t_max - t_min)), 0, 255).astype(np.uint8)
            t_large = cv2.resize(t_norm, IMG_SIZE, interpolation=cv2.INTER_CUBIC)
            color_therm = cv2.applyColorMap(t_large, cv2.COLORMAP_JET)
            disp_therm = cv2.resize(color_therm, (640, 480), interpolation=cv2.INTER_NEAREST)
        
        now = time.time()
        cam_boxes = None
        therm_boxes = None

        # 3. 摄像头分频推理，框结果短暂缓存，避免每帧都跑 NPU
        if img_cam is not None and (frame_count % CAMERA_INFER_INTERVAL == 0):
            try:
                cam_resized = cv2.resize(img_cam, IMG_SIZE)
                cam_rgb = cv2.cvtColor(cam_resized, cv2.COLOR_BGR2RGB)
                out = rknn_cam.inference(inputs=[np.expand_dims(cam_rgb, axis=0)])
                cam_boxes, _ = post_process(out)
                if cam_boxes is not None:
                    last_cam_boxes = cam_boxes.copy()
                    last_cam_detect_time = now
                elif now - last_cam_detect_time > BOX_HOLD_SEC:
                    last_cam_boxes = None
            except Exception as e:
                print(f"摄像头推理异常: {e}")

        # 4. 热成像在 SEARCH 时低频推理，在 VERIFY 时提高频率
        thermal_interval = THERMAL_INFER_INTERVAL_VERIFY if mode == "VERIFY" else THERMAL_INFER_INTERVAL_IDLE
        if img_therm is not None and (frame_count % thermal_interval == 0):
            try:
                t_norm = np.clip((img_therm - 25.0) * (255.0 / 10.0), 0, 255).astype(np.uint8)
                t_large = cv2.resize(t_norm, IMG_SIZE)
                color_therm = cv2.applyColorMap(t_large, cv2.COLORMAP_JET)
                t_rgb = cv2.cvtColor(color_therm, cv2.COLOR_BGR2RGB)
                out_t = rknn_therm.inference(inputs=[np.expand_dims(t_rgb, axis=0)])
                therm_boxes, _ = post_process(out_t)
                if therm_boxes is not None:
                    last_therm_boxes = therm_boxes.copy()
                    last_therm_detect_time = now
                elif now - last_therm_detect_time > BOX_HOLD_SEC:
                    last_therm_boxes = None
            except Exception as e:
                print(f"热成像推理异常: {e}")

        # 5. 用缓存框持续绘制，保证画面上一直有框
        if last_cam_boxes is not None and now - last_cam_detect_time <= BOX_HOLD_SEC:
            scale_w = 1.0
            scale_h = 480.0 / 640.0
            for box in last_cam_boxes:
                x1, y1, x2, y2 = box.astype(int)
                x1d = max(0, int(x1 * scale_w))
                y1d = max(0, int(y1 * scale_h))
                x2d = min(640, int(x2 * scale_w))
                y2d = min(480, int(y2 * scale_h))
                cv2.rectangle(disp_cam, (x1d, y1d), (x2d, y2d), (0, 0, 255), 2)
                cv2.putText(disp_cam, "PERSON", (x1d, max(20, y1d - 10)),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        elif now - last_cam_detect_time > BOX_HOLD_SEC:
            last_cam_boxes = None

        if last_therm_boxes is not None and now - last_therm_detect_time <= BOX_HOLD_SEC:
            scale_t_w = 1.0
            scale_t_h = 480.0 / 640.0
            for box in last_therm_boxes:
                x1, y1, x2, y2 = box.astype(int)
                x1d = max(0, int(x1 * scale_t_w))
                y1d = max(0, int(y1 * scale_t_h))
                x2d = min(640, int(x2 * scale_t_w))
                y2d = min(480, int(y2 * scale_t_h))
                cv2.rectangle(disp_therm, (x1d, y1d), (x2d, y2d), (0, 255, 0), 2)
                cv2.putText(disp_therm, "PERSON", (x1d, max(20, y1d - 10)),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        elif now - last_therm_detect_time > BOX_HOLD_SEC:
            last_therm_boxes = None

        # 6. 状态机只看缓存结果，避免因为分频推理出现闪断
        cam_active = last_cam_boxes is not None and now - last_cam_detect_time <= BOX_HOLD_SEC
        therm_active = last_therm_boxes is not None and now - last_therm_detect_time <= BOX_HOLD_SEC

        if mode == "SEARCH":
            if cam_active:
                print("--> [NPU] 摄像头发现目标，拉起热成像验证")
                mode = "VERIFY"
                verify_start_time = now

        elif mode == "VERIFY":
            if cam_active and therm_active:
                print("--> [NPU] 双路确认！触发报警")
                if now - state['last_trigger'] > COOLDOWN:
                    state['last_trigger'] = now
                    threading.Thread(target=save_and_send, args=(disp_therm.copy(), disp_cam.copy(), "dual_detected"), daemon=True).start()
                mode = "COOLDOWN"
            elif cam_active and (not therm_active) and (now - verify_start_time >= SUSPECT_NO_VITAL_VERIFY_SEC):
                print("--> [NPU] 热成像未确认，疑似无生命体征，触发报警")
                if now - state['last_trigger'] > COOLDOWN:
                    state['last_trigger'] = now
                    threading.Thread(target=save_and_send, args=(disp_therm.copy(), disp_cam.copy(), "suspect_no_vital"), daemon=True).start()
                mode = "COOLDOWN"
            elif not cam_active:
                print("--> [NPU] 摄像头目标丢失，返回搜索")
                mode = "SEARCH"

        elif mode == "COOLDOWN":
            if now - state['last_trigger'] > COOLDOWN:
                print("--> [NPU] 冷却结束")
                mode = "SEARCH"
        
        # 4. 更新全局帧
        with lock:
            state['thermal_frame'] = disp_therm
            state['camera_frame'] = disp_cam
        
        time.sleep(0.01)

# ==================== 6. 报警发送 ====================
def save_and_send(frm_t, frm_c, status):
    try:
        ts = time.strftime("%Y%m%d_%H%M%S")
        p_t = os.path.join(SAVE_DIR, f"{ts}_thermal.jpg")
        p_c = os.path.join(SAVE_DIR, f"{ts}_camera.jpg")
        cv2.imwrite(p_c, frm_c)
        if status != "suspect_no_vital":
            cv2.imwrite(p_t, frm_t)

        ok, msg = camera_digest_alarm.trigger_speech_alarm(
            host=CAMERA_HTTP_HOST,
            username=CAMERA_HTTP_USER,
            password=CAMERA_HTTP_PASS,
            sound_id=CAMERA_ALARM_SOUND_ID,
            ch=CAMERA_ALARM_CH,
            dev=CAMERA_ALARM_DEV,
            timeout=3.0,
        )
        if ok:
            print(f"--> [摄像头报警] 已触发: {msg}")
        else:
            print(f"--> [摄像头报警] 触发失败: {msg}")
        
        print(f"--> [上传] 正在发送至安卓端 {ANDROID_URL}")
        try:
            if status == "suspect_no_vital":
                with open(p_c, 'rb') as f_c:
                    response = requests.post(
                        ANDROID_URL,
                        files={'camera': ('camera.jpg', f_c, 'image/jpeg')},
                        data={'timestamp': ts, 'status': status},
                        timeout=10.0
                    )
                    print(f"--> [上传] 响应码: {response.status_code}, 内容: {response.text}")
            else:
                with open(p_t, 'rb') as f_t, open(p_c, 'rb') as f_c:
                    response = requests.post(
                        ANDROID_URL,
                        files={
                            'thermal': ('thermal.jpg', f_t, 'image/jpeg'),
                            'camera': ('camera.jpg', f_c, 'image/jpeg')
                        },
                        data={'timestamp': ts, 'status': status},
                        timeout=10.0
                    )
                    print(f"--> [上传] 响应码: {response.status_code}, 内容: {response.text}")
        except Exception as req_e:
            print(f"--> [上传] 请求失败: {req_e}")
        print(f"--> [上传] 完成")
    except Exception as e:
        print(f"上传异常: {e}")
        import traceback
        traceback.print_exc()

# ==================== 7. Flask Web ====================
def gen_thermal():
    encode = [int(cv2.IMWRITE_JPEG_QUALITY), 80]
    while True:
        with lock:
            f = state['thermal_frame'].copy()
        _, jpg = cv2.imencode('.jpg', f, encode)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpg.tobytes() + b'\r\n')

def gen_camera():
    encode = [int(cv2.IMWRITE_JPEG_QUALITY), 80]
    while True:
        with lock:
            f = state['camera_frame'].copy()
        _, jpg = cv2.imencode('.jpg', f, encode)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpg.tobytes() + b'\r\n')

@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RK3588 Dual NPU</title>
    <style>
        body { background: #2c3e50; color: white; font-family: Arial; margin: 0; padding: 10px; text-align: center; }
        .container { display: flex; flex-wrap: wrap; gap: 15px; justify-content: center; }
        .video-box { flex: 1; min-width: 300px; max-width: 640px; position: relative; background: black; border: 3px solid #34495e; border-radius: 8px; overflow: hidden; aspect-ratio: 4/3; }
        .video-box img { width: 100%; height: 100%; object-fit: contain; display: block; }
        .label { position: absolute; top: 10px; left: 10px; background: rgba(0,0,0,0.6); padding: 4px 8px; border-radius: 4px; font-size: 12px; }
    </style>
    </head>
    <body>
        <h1>RK3588 NPU 推理系统</h1>
        <div class="container">
            <div class="video-box"><img src="/thermal_feed"><div class="label">热成像</div></div>
            <div class="video-box"><img src="/camera_feed"><div class="label">可见光</div></div>
        </div>
    </body></html>
    """

@app.route('/thermal_feed')
def thermal_feed():
    return Response(gen_thermal(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/camera_feed')
def camera_feed():
    return Response(gen_camera(), mimetype='multipart/x-mixed-replace; boundary=frame')

# ==================== 8. 启动入口 ====================
if __name__ == '__main__':
    print("="*40)
    print("  RK3588 NPU 双路推理系统")
    print("="*40)
    
    # 初始化 NPU
    rknn_therm, rknn_cam = init_npus()
    if not rknn_therm or not rknn_cam:
        print("NPU 初始化失败！")
        sys.exit(1)
    
    # 初始化串口
    ser_obj = None
    try:
        print("--> 打开串口...")
        ser_obj = serial.Serial(PORT, BAUD, timeout=0.01)
        ser_obj.write(bytes([0x5A, 0x01, 0x01]))
        print("--> 串口 OK")
    except Exception as e:
        print(f"串口初始化失败: {e}")
    
    # 启动线程
    threading.Thread(target=thermal_capture, args=(ser_obj,), daemon=True).start()
    threading.Thread(target=camera_capture, daemon=True).start()
    threading.Thread(target=main_loop, args=(rknn_therm, rknn_cam), daemon=True).start()
    
    try:
        app.run(host='0.0.0.0', port=5001, threaded=True, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("\n正在退出...")
        state['running'] = False
        time.sleep(0.5)
        if ser_obj:
            try: ser_obj.close()
            except: pass
