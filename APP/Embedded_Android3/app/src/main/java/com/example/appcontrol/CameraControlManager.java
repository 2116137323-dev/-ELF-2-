package com.example.appcontrol;

import java.io.IOException;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import okhttp3.Authenticator;
import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import okhttp3.Route;

/**
 * 摄像头 HTTP 控制管理类。
 *
 * 负责调用摄像头私有 HTTP 接口控制云台和补光灯。
 * 云台接口使用标准 Digest 鉴权，补光灯接口使用摄像头固件自定义的 X-Digest 鉴权。
 */
public class CameraControlManager {
    private final OkHttpClient clientPtz;
    private final OkHttpClient clientLight;
    private static final MediaType JSON = MediaType.parse("application/json; charset=utf-8");

    /**
     * 分别构造云台和补光灯请求客户端，因为两个接口的鉴权头格式不同。
     */
    public CameraControlManager(String user, String pwd) {
        clientPtz = new OkHttpClient.Builder()
                .connectTimeout(2, TimeUnit.SECONDS)
                .writeTimeout(2, TimeUnit.SECONDS)
                .readTimeout(2, TimeUnit.SECONDS)
                .authenticator(new DigestAuthenticator(user, pwd))
                .build();
        clientLight = new OkHttpClient.Builder()
                .connectTimeout(2, TimeUnit.SECONDS)
                .writeTimeout(2, TimeUnit.SECONDS)
                .readTimeout(2, TimeUnit.SECONDS)
                .authenticator(new XDigestAuthenticator(user, pwd))
                .build();
    }

    /**
     * 发送云台控制命令。
     *
     * cmd 表示摄像头固件定义的方向/动作码，stop 表示是否停止当前动作。
     */
    public void ptzControl(String url, int cmd, int stop) {
        String json = "{\n  \"Type\":1,\n  \"Ch\":1,\n  \"Dev\":1,\n  \"Data\":{\n    \"Cmd\":" + cmd + ",\n    \"IsStop\":" + stop + ",\n    \"Speed\":10\n  }\n}";
        RequestBody body = RequestBody.create(json, JSON);
        Request req = new Request.Builder().url(url).post(body).addHeader("User-Agent", "curl/4.7.1").build();
        clientPtz.newCall(req).enqueue(cb());
    }

    /**
     * 控制摄像头补光灯。
     *
     * control=1 打开补光灯，control=0 关闭补光灯；亮度和模式按项目硬件固定值发送。
     */
    public void lightControl(String url, int control) {
        String json = "{\n  \"Type\":1,\n  \"Dev\":1,\n  \"Ch\":1,\n  \"Data\":{\n    \"LightOffTime\":0,\n    \"LightOnTime\":0,\n    \"Brightness\":81,\n    \"Mode\":\"Warm\",\n    \"Control\":" + control + ",\n    \"ModeSupportList\":[\"Ir\",\"Warm\",\"Ir_Warm\"]\n  }\n}";
        RequestBody body = RequestBody.create(json, JSON);
        Request req = new Request.Builder().url(url).post(body).addHeader("User-Agent", "Mozilla/5.0").addHeader("Content-Type", "application/json;charset=UTF-8").build();
        clientLight.newCall(req).enqueue(cb());
    }

    /**
     * 通用异步回调：控制类请求只关心是否发出，响应体无需处理，及时关闭 Response 防止泄漏。
     */
    private Callback cb() {
        return new Callback() {
            @Override public void onFailure(Call c, IOException e) { e.printStackTrace(); }
            @Override public void onResponse(Call c, Response r) throws IOException { r.close(); }
        };
    }

    /**
     * 标准 HTTP Digest 鉴权实现，用于云台接口。
     */
    public static class DigestAuthenticator implements Authenticator {
        private final String user, pwd;
        private int nonceCount = 0;
        public DigestAuthenticator(String u, String p) { user = u; pwd = p; }

        @Override
        public Request authenticate(Route route, Response resp) throws IOException {
            // OkHttp 收到 401 后进入这里，根据 WWW-Authenticate 计算 Authorization 后重试一次。
            String auth = resp.header("WWW-Authenticate");
            if (auth == null || !auth.startsWith("Digest") || resp.priorResponse() != null) return null;
            Map<String, String> pm = parse(auth.substring(7));
            String realm = pm.get("realm");
            String nonce = pm.get("nonce");
            String qop = pm.get("qop");
            String opaque = pm.get("opaque");
            String alg = pm.get("algorithm");
            if (alg == null) alg = "MD5";

            String method = resp.request().method();
            String uri = resp.request().url().encodedPath();
            if (resp.request().url().encodedQuery() != null) uri += "?" + resp.request().url().encodedQuery();
            nonceCount++;
            String nc = String.format("%08x", nonceCount);
            String cnonce = UUID.randomUUID().toString().substring(0, 8);

            // Digest 计算公式：HA1=MD5(user:realm:pwd)，HA2=MD5(method:uri)。
            String ha1 = md5(user + ":" + realm + ":" + pwd);
            String ha2 = md5(method + ":" + uri);
            String res;
            if ("auth".equals(qop)) res = md5(ha1 + ":" + nonce + ":" + nc + ":" + cnonce + ":" + qop + ":" + ha2);
            else res = md5(ha1 + ":" + nonce + ":" + ha2);

            StringBuilder sb = new StringBuilder();
            sb.append("Digest username=\"").append(user).append("\", ");
            sb.append("realm=\"").append(realm).append("\", ");
            sb.append("nonce=\"").append(nonce).append("\", ");
            sb.append("uri=\"").append(uri).append("\", ");
            sb.append("response=\"").append(res).append("\"");
            if (opaque != null) sb.append(", opaque=\"").append(opaque).append("\"");
            if (qop != null) sb.append(", qop=").append(qop).append(", nc=").append(nc).append(", cnonce=\"").append(cnonce).append("\"");
            if (alg != null) sb.append(", algorithm=").append(alg);

            return resp.request().newBuilder().header("Authorization", sb.toString()).build();
        }

        /**
         * 解析 WWW-Authenticate 头中的逗号分隔键值对。
         */
        private Map<String, String> parse(String s) {
            Map<String, String> map = new HashMap<>();
            for (String p : s.split(",\\s*")) {
                String[] kv = p.split("=", 2);
                if (kv.length == 2) map.put(kv[0].trim(), kv[1].trim().replace("\"", ""));
            }
            return map;
        }

        /**
         * 计算 MD5 十六进制字符串，用于 Digest response 字段。
         */
        private String md5(String s) {
            try {
                MessageDigest md = MessageDigest.getInstance("MD5");
                byte[] b = md.digest(s.getBytes());
                StringBuilder sb = new StringBuilder();
                for (byte v : b) {
                    String h = Integer.toHexString(0xFF & v);
                    if (h.length() == 1) sb.append('0');
                    sb.append(h);
                }
                return sb.toString();
            } catch (Exception e) { return ""; }
        }
    }

    /**
     * 摄像头补光灯接口使用的自定义 X-Digest 鉴权实现。
     */
    public static class XDigestAuthenticator implements Authenticator {
        private final String user, pwd;
        private int nonceCount = 0;
        public XDigestAuthenticator(String u, String p) { user = u; pwd = p; }

        @Override
        public Request authenticate(Route route, Response resp) throws IOException {
            // X-Digest 与标准 Digest 字段基本一致，但 Authorization 前缀必须使用 X-Digest。
            String auth = resp.header("WWW-Authenticate");
            if (auth == null || !auth.startsWith("X-Digest") || resp.priorResponse() != null) return null;
            Map<String, String> pm = parse(auth.substring(8));
            String realm = pm.get("realm");
            String nonce = pm.get("nonce");
            String qop = pm.get("qop");
            String opaque = pm.get("opaque");
            String uri = resp.request().url().encodedPath();

            nonceCount++;
            String nc = String.format("%08x", nonceCount);
            String cnonce = UUID.randomUUID().toString().substring(0, 16);
            String ha1 = md5(user + ":" + realm + ":" + pwd);
            String ha2 = md5(resp.request().method() + ":" + uri);
            String res = md5(ha1 + ":" + nonce + ":" + nc + ":" + cnonce + ":" + qop + ":" + ha2);

            String val = "X-Digest " + "username=\"" + user + "\", realm=\"" + realm + "\", nonce=\"" + nonce + "\", uri=\"" + uri + "\", " +
                    "response=\"" + res + "\", opaque=\"" + opaque + "\", qop=" + qop + ", nc=" + nc + ", cnonce=\"" + cnonce + "\"";
            return resp.request().newBuilder().header("Authorization", val).build();
        }

        private Map<String, String> parse(String s) {
            Map<String, String> map = new HashMap<>();
            for (String p : s.split(",\\s*")) {
                String[] kv = p.split("=", 2);
                if (kv.length == 2) map.put(kv[0].trim(), kv[1].trim().replace("\"", ""));
            }
            return map;
        }

        private String md5(String s) {
            try {
                MessageDigest md = MessageDigest.getInstance("MD5");
                byte[] b = md.digest(s.getBytes());
                StringBuilder sb = new StringBuilder();
                for (byte v : b) {
                    String h = Integer.toHexString(0xFF & v);
                    if (h.length() == 1) sb.append('0');
                    sb.append(h);
                }
                return sb.toString();
            } catch (Exception e) { return ""; }
        }
    }
}
