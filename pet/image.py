"""
017Pet — 图片/GIF 发送模块
iLink image_item (type=2) 通过 CDN + AES-128-ECB 加密上传
"""

import os
import json
import time
import random
import base64
import hashlib
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError, URLError
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

# 绕过 Clash 代理
for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"]:
    os.environ.pop(key, None)
os.environ["no_proxy"] = "*"
_opener = build_opener(ProxyHandler({}))

BASE_URL = "https://ilinkai.weixin.qq.com"


def _random_uin():
    n = random.randint(0, 0xFFFFFFFF)
    return base64.b64encode(str(n).encode()).decode()


def _make_headers(bot_token):
    return {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {bot_token}",
        "X-WECHAT-UIN": _random_uin(),
    }


def _api_request(method, path, body=None, headers=None, timeout=15):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = Request(url, data=data, headers=headers or {}, method=method)
    try:
        with _opener.open(req, timeout=timeout) as resp:
            raw = resp.read()
            result = json.loads(raw.decode("utf-8")) if raw else {}
            ret = result.get("ret")
            if ret is not None and ret != 0:
                print(f"  API ret={ret}: {path}")
                result["_ret_error"] = ret
            return result
    except HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        print(f"  HTTP {e.code}: {body_text[:300]}")
        return {"error": e.code}
    except Exception as e:
        print(f"  请求失败: {e}")
        return {"error": str(e)}


# ============================================================
# 加密
# ============================================================
def _encrypt_file(file_bytes):
    """AES-128-ECB + PKCS7 加密文件，返回加密信息 dict"""
    aes_key = os.urandom(16)
    # Format B: base64(hex string) — WeChat SDK 标准格式
    aes_key_b64 = base64.b64encode(aes_key.hex().encode()).decode()

    # PKCS7 padding
    padder = padding.PKCS7(128).padder()
    padded = padder.update(file_bytes) + padder.finalize()

    # AES-128-ECB 加密
    cipher = Cipher(algorithms.AES(aes_key), modes.ECB())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    return {
        "ciphertext": ciphertext,
        "aes_key_b64": aes_key_b64,
        "aes_key_hex": aes_key.hex(),
        "rawsize": len(file_bytes),
        "filesize": len(ciphertext),
        "rawfilemd5": hashlib.md5(file_bytes).hexdigest(),
        "filekey": os.urandom(8).hex(),
    }


# ============================================================
# CDN 上传
# ============================================================
def _get_upload_url(state, to_user_id, enc_info, media_type=1):
    """获取 CDN 上传 URL，media_type: 1=图片 2=视频 3=文件 4=语音"""
    body = {
        "to_user_id": to_user_id,
        "media_type": media_type,
        "rawsize": enc_info["rawsize"],
        "rawfilemd5": enc_info["rawfilemd5"],
        "filesize": enc_info["filesize"],
        "filekey": enc_info["filekey"],
        "aeskey": enc_info["aes_key_hex"],
        "no_need_thumb": True,
        "base_info": {"channel_version": "1.0.0"},
    }
    resp = _api_request("POST", "/ilink/bot/getuploadurl", body=body,
                        headers=_make_headers(state["bot_token"]))
    # 调试：打印完整响应
    resp_keys = list(resp.keys()) if isinstance(resp, dict) else []
    print(f"  getuploadurl 响应字段: {resp_keys}")

    # API 可能返回 upload_param 或 encrypt_query_param
    upload_param = (resp.get("upload_param") or resp.get("encrypt_query_param") or "")
    upload_url = resp.get("upload_url", "")

    if upload_param and "error" not in resp:
        return {
            "upload_url": upload_url,
            "upload_param": upload_param,
        }
    print(f"  getuploadurl 失败: {resp}")
    return None


def _upload_to_cdn(upload_url, ciphertext):
    """上传加密数据到 CDN（POST），返回 x-encrypted-param 或 None"""
    req = Request(upload_url, data=ciphertext, method="POST")
    req.add_header("Content-Type", "application/octet-stream")
    try:
        with _opener.open(req, timeout=30) as resp:
            if resp.status in (200, 201, 204):
                # 关键：CDN 返回的 x-encrypted-param 才是 sendmessage 要用的
                encrypted_param = resp.headers.get("x-encrypted-param", "")
                print(f"  CDN x-encrypted-param: {encrypted_param[:50]}{'...' if len(encrypted_param)>50 else ''}")
                return encrypted_param or True
            print(f"  CDN 上传返回: {resp.status}")
            return None
    except HTTPError as e:
        print(f"  CDN 上传 HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}")
        return None
    except Exception as e:
        print(f"  CDN 上传失败: {e}")
        return None


# ============================================================
# 发送图片消息
# ============================================================
def send_image(state, to_user_id, context_token, image_bytes):
    """
    完整图片发送流程：加密→获取URL→上传CDN→发消息
    image_bytes: 图片的原始字节数据
    返回 True/False
    """
    print(f"  [图片] 加密中... ({len(image_bytes)} bytes)")
    enc_info = _encrypt_file(image_bytes)

    print(f"  [图片] 获取上传 URL...")
    upload_info = _get_upload_url(state, to_user_id, enc_info, media_type=1)
    if not upload_info:
        return False

    # 构造 CDN 上传 URL
    from urllib.parse import quote
    CDN_BASE = "https://novac2c.cdn.weixin.qq.com/c2c"
    param = quote(upload_info["upload_param"], safe="")
    cdn_url = f"{CDN_BASE}/upload?encrypted_query_param={param}&filekey={enc_info['filekey']}"
    print(f"  [图片] 上传到 CDN...")
    cdn_result = _upload_to_cdn(cdn_url, enc_info["ciphertext"])
    if not cdn_result:
        return False

    # 优先用 CDN 返回的 x-encrypted-param，否则用原始 upload_param
    final_param = cdn_result if isinstance(cdn_result, str) else upload_info["upload_param"]

    print(f"  [图片] 发送消息...")
    client_id = f"pet-img:{int(time.time()*1000)}-{random.randint(10000000,99999999):08x}"
    body = {
        "msg": {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": client_id,
            "message_type": 2,
            "message_state": 2,
            "context_token": context_token,
            "item_list": [{
                "type": 2,
                "image_item": {
                    "media": {
                        "encrypt_query_param": final_param,
                        "aes_key": enc_info["aes_key_b64"],
                        "encrypt_type": 1,
                    },
                    "aeskey": enc_info["aes_key_hex"],
                    "mid_size": enc_info["filesize"],
                }
            }],
        },
        "base_info": {"channel_version": "1.0.0"},
    }
    resp = _api_request("POST", "/ilink/bot/sendmessage", body=body,
                        headers=_make_headers(state["bot_token"]))
    # sendmessage 成功时响应体为空 {} 或 ret=0
    if resp is not None and "error" not in resp and "_ret_error" not in resp:
        print(f"  [图片] 发送成功 ✓")
        return True
    print(f"  [图片] sendmessage 失败: {resp}")
    return False


MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB


def send_image_file(state, to_user_id, context_token, file_path):
    """从文件路径发送图片"""
    file_size = os.path.getsize(file_path)
    if file_size > MAX_IMAGE_SIZE:
        print(f"  [图片] 文件过大 ({file_size / 1024 / 1024:.1f}MB > 10MB): {file_path}")
        return False
    with open(file_path, "rb") as f:
        return send_image(state, to_user_id, context_token, f.read())
