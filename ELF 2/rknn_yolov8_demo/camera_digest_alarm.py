"""
摄像头 HTTP Digest 摘要鉴权与语音报警触发工具。

该模块用于适配摄像头私有接口：先访问登录接口拿到 WWW-Authenticate，
再手动计算 Digest Authorization，最后调用语音报警配置接口播放指定音频。
"""

import hashlib
import re
import secrets
from typing import Dict, Optional, Tuple

import requests


def _md5_hex(s: str) -> str:
    """计算 Digest 鉴权中需要的 MD5 十六进制摘要。"""
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _parse_www_authenticate(v: str) -> Dict[str, str]:
    """解析服务端返回的 WWW-Authenticate 头，提取 realm、nonce、qop 等字段。"""
    v = v.strip()
    if v.lower().startswith("digest "):
        v = v[7:]

    # 支持 key="value" 与 key=value 两种格式；逗号作为字段分隔符。
    parts = re.findall(r'(\w+)=(".*?"|[^,]+)', v)
    out: Dict[str, str] = {}
    for k, raw in parts:
        raw = raw.strip()
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]
        out[k] = raw
    return out


def _pick_qop(qop_value: str) -> str:
    """从服务端提供的 qop 列表中优先选择 auth。"""
    q = (qop_value or "").strip()
    if not q:
        return "auth"

    parts = [p.strip() for p in q.split(",") if p.strip()]
    if "auth" in parts:
        return "auth"
    return parts[0] if parts else "auth"


def _build_digest_authorization(
    *,
    username: str,
    password: str,
    method: str,
    uri: str,
    realm: str,
    nonce: str,
    qop: str,
    opaque: Optional[str],
    algorithm: Optional[str],
    nc: str,
    cnonce: str,
) -> str:
    """按 RFC Digest 规则生成 Authorization 请求头。"""
    # HA1 = MD5(username:realm:password)，HA2 = MD5(method:uri)。
    ha1 = _md5_hex(f"{username}:{realm}:{password}")
    ha2 = _md5_hex(f"{method}:{uri}")
    response = _md5_hex(f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}")

    # 摄像头接口对字段顺序通常不敏感，但保持常见顺序便于抓包比对。
    items = [
        f'username="{username}"',
        f'realm="{realm}"',
        f'nonce="{nonce}"',
        f'uri="{uri}"',
        f'response="{response}"',
        f'cnonce="{cnonce}"',
    ]
    if opaque:
        items.append(f'opaque="{opaque}"')
    if algorithm:
        items.append(f'algorithm="{algorithm}"')
    items.append(f"qop={qop}")
    items.append(f"nc={nc}")
    return "Digest " + ", ".join(items)


def _digest_post(
    *,
    base: str,
    uri: str,
    username: str,
    password: str,
    json_body: Dict,
    timeout: float,
    headers: Dict[str, str],
) -> Tuple[int, str]:
    """
    发送一次带 Digest 鉴权的 POST 请求。

    流程：
    1. 先不带 Authorization 请求一次，摄像头返回 401 与 WWW-Authenticate。
    2. 解析鉴权参数并计算 Authorization。
    3. 带 Authorization 再请求一次，返回最终响应。
    """
    url = base + uri

    r1 = requests.post(url, json=json_body, headers=headers, timeout=timeout)
    if r1.status_code != 401:
        return r1.status_code, r1.text

    www = r1.headers.get("WWW-Authenticate") or r1.headers.get("Www-Authenticate")
    if not www:
        return r1.status_code, r1.text

    auth = _parse_www_authenticate(www)
    realm = auth.get("realm", "webserver")
    nonce = auth.get("nonce")
    qop = _pick_qop(auth.get("qop", "auth"))
    opaque = auth.get("opaque")
    algorithm = auth.get("algorithm", "MD5")
    if not nonce:
        return r1.status_code, r1.text

    # nc 表示 nonce 使用次数；此处每次完整流程都重新获取 nonce，因此固定值即可。
    nc = "00000002"
    cnonce = secrets.token_hex(8)
    authorization = _build_digest_authorization(
        username=username,
        password=password,
        method="POST",
        uri=uri,
        realm=realm,
        nonce=nonce,
        qop=qop,
        opaque=opaque,
        algorithm=algorithm,
        nc=nc,
        cnonce=cnonce,
    )

    headers2 = dict(headers)
    headers2["Authorization"] = authorization
    r2 = requests.post(url, json=json_body, headers=headers2, timeout=timeout)
    return r2.status_code, r2.text


def trigger_speech_alarm(
    *,
    host: str,
    username: str,
    password: str,
    sound_id: int = 1,
    ch: int = 1,
    dev: int = 1,
    timeout: float = 3.0,
) -> Tuple[bool, str]:
    """
    触发摄像头语音报警。

    返回值：
    - True/False：报警接口是否返回 200。
    - str：包含登录或报警接口响应信息，便于主程序打印诊断。
    """
    base = host.strip()
    if not base.startswith("http://") and not base.startswith("https://"):
        base = "http://" + base

    login_uri = "/digest/frmUserLogin"
    alarm_uri = "/digest/frmSpeechAlarmCfg"

    # 保持与摄像头 Web 接口期望一致的请求头；部分固件对 User-Agent 较敏感。
    headers = {
        "User-Agent": "curl/4.7.1",
        "Content-Type": "application/json; charset=utf-8",
        "Accept-Encoding": "gzip",
    }
    try:
        # 先登录建立认证上下文，避免直接调用报警接口在部分固件上失败。
        login_status, login_text = _digest_post(
            base=base,
            uri=login_uri,
            username=username,
            password=password,
            json_body={"Type": 0, "Ch": 0, "Data": {}},
            timeout=timeout,
            headers=headers,
        )
        if login_status != 200:
            return False, f"login_status:{login_status}:{login_text}"

        # SoundId 指定摄像头中预置的语音文件，Ch/Dev 指定输出通道与设备。
        alarm_status, alarm_text = _digest_post(
            base=base,
            uri=alarm_uri,
            username=username,
            password=password,
            json_body={"Type": 1, "Ch": int(ch), "Dev": int(dev), "Data": {"SoundId": int(sound_id)}},
            timeout=timeout,
            headers=headers,
        )
        return alarm_status == 200, f"alarm_status:{alarm_status}:{alarm_text}"
    except Exception as e:
        return False, f"digest_flow_failed: {e}"
