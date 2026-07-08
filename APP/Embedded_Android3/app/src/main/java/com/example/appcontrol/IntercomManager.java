package com.example.appcontrol;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.AudioAttributes;
import android.media.AudioTrack;
import android.media.MediaRecorder;
import android.media.audiofx.AcousticEchoCanceler;
import android.media.audiofx.AutomaticGainControl;
import android.media.audiofx.NoiseSuppressor;
import android.os.Handler;
import android.os.Looper;
import android.widget.Toast;

import androidx.core.app.ActivityCompat;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

/**
 * 摄像头双向语音对讲管理类。
 *
 * 功能分为两路：
 * 1. 监听：通过 RTSP/RTP over TCP 拉取摄像头音频，G.711u 解码为 PCM 后用 AudioTrack 播放。
 * 2. 对讲：通过 AudioRecord 采集手机麦克风 PCM，编码成 G.711u，再封装 RTP 发送到摄像头回传通道。
 */
public class IntercomManager {
    private final Context context;
    private final String cameraIp;
    private final int rtspPort;
    private final String pathAudioIn;
    private final String pathAudioOut;

    // 摄像头音频通道使用 8kHz 单声道 G.711u，这是安防摄像头常见语音参数。
    private static final int SAMPLE_RATE = 8000;
    private static final float LISTEN_VOLUME_BOOST = 1.35f;
    private static final int TALK_VOLUME_GAIN = 2;
    private static final float TRACK_VOLUME = 0.78f;

    // 播放和录音各自独立加锁，防止停止释放资源时后台线程仍在读写 native 音频对象。
    private final Object listenLock = new Object();
    private final Object talkLock = new Object();

    private Socket socketListen, socketTalk;
    private AudioTrack audioTrack;
    private AudioRecord audioRecord;
    private AcousticEchoCanceler acousticEchoCanceler;
    private NoiseSuppressor noiseSuppressor;
    private AutomaticGainControl automaticGainControl;
    private volatile boolean isListening = false, isTalking = false;

    // RTSP CSeq 分别记录监听与对讲链路的请求序号；RTP 序号和时间戳用于构造回传音频包。
    private int cSeqListen = 1, cSeqTalk = 1;
    private int rtpSeqTalk = 0;
    private long timestampTalk = 0;

    /**
     * 通知 Activity 更新按钮状态或展示错误。
     */
    public interface IntercomCallback {
        void onListenStopped();
        void onTalkStopped();
        void onError(String message);
    }

    private IntercomCallback callback;

    public IntercomManager(Context context, String cameraIp, int rtspPort, String pathAudioIn, String pathAudioOut) {
        this.context = context;
        this.cameraIp = cameraIp;
        this.rtspPort = rtspPort;
        this.pathAudioIn = pathAudioIn;
        this.pathAudioOut = pathAudioOut;
    }

    public void setCallback(IntercomCallback callback) {
        this.callback = callback;
    }

    public boolean isListening() { return isListening; }
    public boolean isTalking() { return isTalking; }

    /**
     * 开启监听摄像头声音。
     *
     * 设置 MODE_IN_COMMUNICATION 和扬声器外放，是为了按通话场景播放，减少系统音频策略干扰。
     */
    public void startListen() {
        isListening = true;
        AudioManager am = (AudioManager) context.getSystemService(Context.AUDIO_SERVICE);
        am.setMode(AudioManager.MODE_IN_COMMUNICATION);
        am.setSpeakerphoneOn(true);
        new Thread(this::listenThread).start();
    }

    /**
     * 停止监听并释放播放端资源。
     */
    public void stopListen() {
        isListening = false;
        try {
            synchronized (listenLock) {
                if (audioTrack != null) {
                    try { audioTrack.stop(); } catch (Exception ignored) {}
                    try { audioTrack.release(); } catch (Exception ignored) {}
                    audioTrack = null;
                }
            }
            if (socketListen != null) {
                try { socketListen.close(); } catch (Exception ignored) {}
                socketListen = null;
            }
            AudioManager am = (AudioManager) context.getSystemService(Context.AUDIO_SERVICE);
            if (am != null) {
                am.setSpeakerphoneOn(false);
                am.setMode(AudioManager.MODE_NORMAL);
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    /**
     * 开启手机到摄像头的语音回传。
     */
    public void startTalk() {
        isTalking = true;
        new Thread(this::talkThread).start();
    }

    /**
     * 停止对讲并释放录音端、音频处理器和 Socket。
     */
    public void stopTalk() {
        isTalking = false;
        try {
            releaseAudioEffects();
            synchronized (talkLock) {
                if (audioRecord != null) {
                    try { audioRecord.stop(); } catch (Exception ignored) {}
                    try { audioRecord.release(); } catch (Exception ignored) {}
                    audioRecord = null;
                }
            }
            if (socketTalk != null) {
                try { socketTalk.close(); } catch (Exception ignored) {}
                socketTalk = null;
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    /**
     * 监听线程：建立 RTSP 会话后持续读取 interleaved RTP 音频包并播放。
     */
    private void listenThread() {
        try {
            socketListen = new Socket();
            socketListen.connect(new InetSocketAddress(cameraIp, rtspPort), 3000);
            socketListen.setSoTimeout(4000);

            InputStream in = socketListen.getInputStream();
            OutputStream out = socketListen.getOutputStream();
            BufferedReader br = new BufferedReader(new InputStreamReader(in));
            cSeqListen = 1;

            // RTSP 标准流程：OPTIONS 探测能力，DESCRIBE 获取 SDP，SETUP 建立 RTP over TCP 通道，PLAY 开始推流。
            sendRtsp(out, br, "OPTIONS rtsp://" + cameraIp + pathAudioIn + " RTSP/1.0", null, true);
            sendRtsp(out, br, "DESCRIBE rtsp://" + cameraIp + pathAudioIn + " RTSP/1.0", null, true, "Accept: application/sdp");
            String setup = sendRtsp(out, br, "SETUP rtsp://" + cameraIp + pathAudioIn + "?ctype=audio RTSP/1.0", null, true, "Transport: RTP/AVP/TCP;unicast;interleaved=0-1");
            String sessionId = parseSession(setup);
            sendRtsp(out, br, "PLAY rtsp://" + cameraIp + pathAudioIn + " RTSP/1.0", sessionId, true);

            synchronized (listenLock) {
                if (!isListening) return;
                initAudioTrack();
                if (audioTrack != null) audioTrack.play();
            }

            byte[] header = new byte[4];
            while (isListening) {
                readFully(in, header, 4);
                // RTSP interleaved frame 格式：'$'、通道号、两字节长度、RTP 数据。
                if (header[0] != 0x24) continue;
                int chan = header[1] & 0xFF;
                int len = ((header[2] & 0xFF) << 8) | (header[3] & 0xFF);

                if (len <= 0 || len > 2048) continue;
                byte[] rtp = new byte[len];
                readFully(in, rtp, len);
                if (chan == 0 && len > 12) {
                    byte[] g711 = new byte[len - 12];
                    System.arraycopy(rtp, 12, g711, 0, g711.length);
                    byte[] pcm = g711uToPcm16(g711);
                    if (isTalking) { java.util.Arrays.fill(pcm, (byte) 0); }
                    // 持锁写入，避免与 stopListen() 的 release() 并发导致 native 崩溃
                    synchronized (listenLock) {
                        AudioTrack track = audioTrack;
                        if (track != null && isListening) {
                            try { track.write(pcm, 0, pcm.length); } catch (Exception ignored) {}
                        }
                    }
                }
            }
        } catch (Exception e) {
            if (isListening) {
                isListening = false;
                handleError("接收音频中断，已自动复位");
                if (callback != null) callback.onListenStopped();
            }
        }
    }

    /**
     * 对讲线程：采集麦克风 PCM，转 G.711u，封装 RTP over TCP 发给摄像头 backchannel。
     */
    private void talkThread() {
        try {
            initAudioRecord();
            if (audioRecord == null || audioRecord.getState() != AudioRecord.STATE_INITIALIZED) {
                handleError("未获得录音权限或硬件未就绪");
                isTalking = false;
                if (callback != null) callback.onTalkStopped();
                return;
            }

            socketTalk = new Socket();
            socketTalk.connect(new InetSocketAddress(cameraIp, rtspPort), 3000);
            OutputStream out = socketTalk.getOutputStream();
            BufferedReader br = new BufferedReader(new InputStreamReader(socketTalk.getInputStream()));
            cSeqTalk = 1; rtpSeqTalk = 0; timestampTalk = 0;

            // 对讲回传使用 ONVIF backchannel，SETUP 时指定 interleaved=4-5。
            sendRtsp(out, br, "OPTIONS rtsp://" + cameraIp + pathAudioOut + " RTSP/1.0", null, false);
            sendRtsp(out, br, "DESCRIBE rtsp://" + cameraIp + pathAudioOut + " RTSP/1.0", null, false, "Accept: application/sdp", "Require: www.onvif.org/ver20/backchannel");
            String setup = sendRtsp(out, br, "SETUP rtsp://" + cameraIp + pathAudioOut + "/?ctype=audioback RTSP/1.0", null, false, "Transport: RTP/AVP/TCP;unicast;interleaved=4-5");
            String sessionId = parseSession(setup);
            sendRtsp(out, br, "PLAY rtsp://" + cameraIp + pathAudioOut + " RTSP/1.0", sessionId, false);

            AudioRecord rec = audioRecord;
            if (rec == null) return;
            rec.startRecording();
            byte[] pcmBuf = new byte[160];
            while (isTalking) {
                int len = rec.read(pcmBuf, 0, pcmBuf.length);
                if (len <= 0) continue;
                byte[] g711 = pcm16ToG711u(pcmBuf);
                byte[] rtp = buildRtp(g711);
                byte[] tcpHeader = {0x24, 0x04, (byte) (rtp.length >> 8), (byte) (rtp.length & 0xFF)};
                out.write(tcpHeader);
                out.write(rtp);
                out.flush();
            }
        } catch (Exception e) {
            if (isTalking) {
                isTalking = false;
                handleError("对讲通讯中断，请重试");
                if (callback != null) callback.onTalkStopped();
            }
        }
    }

    /**
     * 发送一条 RTSP 请求并读取响应头和可选响应体。
     */
    private String sendRtsp(OutputStream out, BufferedReader br, String first, String sess, boolean isListen, String... heads) throws IOException {
        StringBuilder sb = new StringBuilder(first).append("\r\n");
        int seq = isListen ? cSeqListen++ : cSeqTalk++;
        sb.append("CSeq: ").append(seq).append("\r\n");
        if (sess != null && !sess.isEmpty()) sb.append("Session: ").append(sess).append("\r\n");
        for (String h : heads) if (!h.isEmpty()) sb.append(h).append("\r\n");
        sb.append("\r\n");
        out.write(sb.toString().getBytes()); out.flush();

        StringBuilder resp = new StringBuilder();
        String line;
        int contentLength = 0;

        while ((line = br.readLine()) != null && !line.isEmpty()) {
            resp.append(line).append("\n");
            if (line.toLowerCase().startsWith("content-length:")) {
                try { contentLength = Integer.parseInt(line.split(":")[1].trim()); } catch (Exception e) { contentLength = 0; }
            }
        }

        if (contentLength > 0) {
            char[] bodyBuf = new char[contentLength];
            int readBytes = 0;
            while (readBytes < contentLength) {
                int read = br.read(bodyBuf, readBytes, contentLength - readBytes);
                if (read == -1) break;
                readBytes += read;
            }
            resp.append(bodyBuf, 0, readBytes);
        }
        return resp.toString();
    }

    /**
     * 从 RTSP SETUP 响应中提取 Session ID，后续 PLAY 请求必须携带该值。
     */
    private String parseSession(String resp) {
        for (String s : resp.split("\n"))
            if (s.startsWith("Session:")) return s.split(":")[1].trim().split(";")[0];
        return "";
    }

    /**
     * 初始化播放端 AudioTrack，用于播放摄像头传来的 PCM 音频。
     */
    private void initAudioTrack() {
        int buf = AudioTrack.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT);
        audioTrack = new AudioTrack.Builder()
                .setAudioAttributes(new AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build())
                .setAudioFormat(new android.media.AudioFormat.Builder()
                        .setSampleRate(SAMPLE_RATE)
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .build())
                .setBufferSizeInBytes(buf * 2)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build();
        audioTrack.setVolume(TRACK_VOLUME);
    }

    /**
     * 初始化录音端 AudioRecord；没有 RECORD_AUDIO 权限时保持 audioRecord 为空。
     */
    private void initAudioRecord() {
        int buf = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
        if (ActivityCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            audioRecord = new AudioRecord(MediaRecorder.AudioSource.VOICE_COMMUNICATION, SAMPLE_RATE,
                    AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, buf);
            enableAudioEffects();
        }
    }

    /**
     * 开启系统音频处理：回声消除和降噪，AGC 关闭以避免音量被系统过度拉伸。
     */
    private void enableAudioEffects() {
        releaseAudioEffects();
        if (audioRecord == null) return;
        int sessionId = audioRecord.getAudioSessionId();
        try {
            if (AcousticEchoCanceler.isAvailable()) {
                acousticEchoCanceler = AcousticEchoCanceler.create(sessionId);
                if (acousticEchoCanceler != null) acousticEchoCanceler.setEnabled(true);
            }
            if (NoiseSuppressor.isAvailable()) {
                noiseSuppressor = NoiseSuppressor.create(sessionId);
                if (noiseSuppressor != null) noiseSuppressor.setEnabled(true);
            }
            if (AutomaticGainControl.isAvailable()) {
                automaticGainControl = AutomaticGainControl.create(sessionId);
                if (automaticGainControl != null) automaticGainControl.setEnabled(false);
            }
        } catch (Exception ignored) {
        }
    }

    /**
     * 释放音频效果器，避免 Activity 退出或重新开启对讲时泄漏 native 资源。
     */
    private void releaseAudioEffects() {
        if (acousticEchoCanceler != null) {
            acousticEchoCanceler.release();
            acousticEchoCanceler = null;
        }
        if (noiseSuppressor != null) {
            noiseSuppressor.release();
            noiseSuppressor = null;
        }
        if (automaticGainControl != null) {
            automaticGainControl.release();
            automaticGainControl = null;
        }
    }

    /**
     * 构造 RTP 包：12 字节 RTP 头 + G.711u 音频负载。
     */
    private byte[] buildRtp(byte[] payload) {
        ByteBuffer buf = ByteBuffer.allocate(12 + payload.length);
        buf.order(ByteOrder.BIG_ENDIAN);
        buf.put((byte) 0x80).put((byte) 0).putShort((short) rtpSeqTalk++);
        buf.putInt((int) timestampTalk).putInt(0x12345678).put(payload);
        timestampTalk += 80;
        return buf.array();
    }

    /**
     * 将 16bit little-endian PCM 转为 G.711u，每两个 PCM 字节压缩为一个 ulaw 字节。
     */
    private byte[] pcm16ToG711u(byte[] pcm) {
        byte[] r = new byte[pcm.length / 2];
        for (int i = 0; i < r.length; i++) {
            short s = (short) ((pcm[i * 2 + 1] << 8) | (pcm[i * 2] & 0xFF));
            int amp = Math.abs(s) < 5000 ? s * TALK_VOLUME_GAIN : (Math.abs(s) < 15000 ? s * Math.max(1, TALK_VOLUME_GAIN / 2) : s);
            amp = Math.max(Short.MIN_VALUE, Math.min(Short.MAX_VALUE, amp));
            r[i] = linear2ulaw((short) amp);
        }
        return r;
    }

    /**
     * 单个 PCM 采样点编码为 G.711 μ-law。
     */
    private byte linear2ulaw(short sample) {
        int sign = (sample >> 8) & 0x80;
        if (sample < 0) sample = (short) -sample;
        if (sample > 32635) sample = 32635;
        sample += 132;
        int exponent = 7;
        for (int expMask = 0x4000; (sample & expMask) == 0; exponent--, expMask >>= 1);
        int mantissa = (sample >> (exponent + 3)) & 0x0F;
        return (byte) ~(sign | (exponent << 4) | mantissa);
    }

    /**
     * 将摄像头发送的 G.711u 音频解码为 16bit little-endian PCM。
     */
    private byte[] g711uToPcm16(byte[] ulaw) {
        byte[] r = new byte[ulaw.length * 2];
        for (int i = 0; i < ulaw.length; i++) {
            short s = ulaw2linear(ulaw[i]);
            float boosted = (float) s * LISTEN_VOLUME_BOOST;
            if (boosted > 32767f) boosted = 32767f;
            if (boosted < -32768f) boosted = -32768f;
            short finalSample = (short) boosted;
            r[i * 2] = (byte) finalSample;
            r[i * 2 + 1] = (byte) (finalSample >> 8);
        }
        return r;
    }

    /**
     * 单个 G.711 μ-law 字节解码为 PCM 采样点。
     */
    private short ulaw2linear(byte ulaw) {
        int u = ~ulaw & 0xFF;
        int sign = (u >> 7) & 1;
        int seg = ((u >> 4) & 7) + 4;
        int pcm = (((u & 15) << 1) + 33) << seg;
        return (short) (sign == 1 ? -pcm : pcm);
    }

    /**
     * 从输入流读取指定长度数据；Socket 流一次 read 不保证读满，所以需要循环读取。
     */
    private void readFully(InputStream in, byte[] b, int len) throws IOException {
        int n = 0;
        while (n < len) {
            int count = in.read(b, n, len - n);
            if (count == -1) throw new IOException("流结束");
            n += count;
        }
    }

    /**
     * 统一错误提示入口，保证 Toast 和回调都在主线程执行。
     */
    private void handleError(String msg) {
        new Handler(Looper.getMainLooper()).post(() -> {
            Toast.makeText(context, msg, Toast.LENGTH_SHORT).show();
            if (callback != null) callback.onError(msg);
        });
    }
}
