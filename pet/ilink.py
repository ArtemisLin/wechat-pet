"""
017Pet — iLink 通信层（保持薄）
只负责：登录、轮询收消息、发送消息
"""

import sys
import io
import json
import time
import random
import base64
import os
import socket
from datetime import datetime, timedelta
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError, URLError

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

# 绕过 Clash 代理
for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"]:
    os.environ.pop(key, None)
os.environ["no_proxy"] = "*"
_opener = build_opener(ProxyHandler({}))

from config import ILINK_STATE_FILE, TIMEZONE, DECAY_INTERVAL_MIN
from pathlib import Path

BASE_URL = "https://ilinkai.weixin.qq.com"
ASSETS_BASE = Path(__file__).parent.parent / "assets"


def _get_assets_dir(species_id="penguin"):
    """按品种返回素材目录。如果品种目录不存在，fallback 到 penguin。"""
    species_dir = ASSETS_BASE / species_id
    if species_dir.is_dir():
        return str(species_dir)
    return str(ASSETS_BASE / "penguin")


# ============================================================
# 底层工具
# ============================================================
def _random_uin():
    n = random.randint(0, 0xFFFFFFFF)
    return base64.b64encode(str(n).encode()).decode()


def _make_headers(bot_token=None):
    headers = {"Content-Type": "application/json"}
    if bot_token:
        headers["AuthorizationType"] = "ilink_bot_token"
        headers["Authorization"] = f"Bearer {bot_token}"
        headers["X-WECHAT-UIN"] = _random_uin()
    return headers


def _api_request(method, path, body=None, headers=None, timeout=10):
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
        print(f"  HTTP {e.code}: {body_text[:200]}")
        return {"error": e.code}
    except (URLError, socket.timeout, TimeoutError):
        return {"timeout": True}
    except (ConnectionError, OSError, KeyboardInterrupt) as e:
        print(f"  连接中断: {type(e).__name__}")
        return {"timeout": True}


# ============================================================
# 状态管理
# ============================================================
def load_state():
    if os.path.exists(ILINK_STATE_FILE):
        with open(ILINK_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(ILINK_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ============================================================
# 登录
# ============================================================
def login():
    """获取二维码 → 等待扫码 → 返回 state"""
    print("\n=== 获取 iLink 登录二维码 ===")
    resp = _api_request("GET", "/ilink/bot/get_bot_qrcode?bot_type=3")
    if not resp or "error" in resp:
        print("  获取失败，检查网络")
        return None

    qrcode = resp.get("qrcode", "")
    qrcode_url = resp.get("qrcode_img_content", "")
    print(f"  二维码链接: {qrcode_url}")
    print(f"\n  >>> 请用微信扫描以上链接中的二维码 <<<")

    headers = {"iLink-App-ClientVersion": "1"}
    start = time.time()
    while time.time() - start < 120:
        resp = _api_request("GET", f"/ilink/bot/get_qrcode_status?qrcode={qrcode}",
                            headers=headers, timeout=35)
        if not resp or resp.get("timeout"):
            continue
        status = resp.get("status", "")
        print(f"  状态: {status}")
        if status == "confirmed":
            state = {
                "bot_token": resp.get("bot_token", ""),
                "bot_id": resp.get("ilink_bot_id", ""),
                "login_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "cursor": "",
                "cached_tokens": {},
            }
            save_state(state)
            print("  登录成功！")
            return state
        if status == "expired":
            print("  二维码已过期")
            return None
        time.sleep(1)

    print("  等待超时")
    return None


# ============================================================
# 发送消息
# ============================================================
def send_message(state, to_user_id, context_token, text):
    """发送文本消息，返回 True/False"""
    client_id = f"pet:{int(time.time()*1000)}-{random.randint(10000000,99999999):08x}"
    body = {
        "msg": {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": client_id,
            "message_type": 2,
            "message_state": 2,
            "context_token": context_token,
            "item_list": [{"type": 1, "text_item": {"text": text}}],
        },
        "base_info": {"channel_version": "1.0.0"},
    }
    resp = _api_request("POST", "/ilink/bot/sendmessage", body=body,
                        headers=_make_headers(state["bot_token"]))
    # sendmessage 成功时响应体可能为空 {}，视为成功
    if resp is not None and "error" not in resp and "timeout" not in resp and "_ret_error" not in resp:
        return True
    print(f"  发送失败: {resp}")
    return False


def _is_token_fresh(info, max_hours=20):
    """检查缓存的 context_token 是否在有效期内（默认 20h，留 4h 安全余量）"""
    cached_time = info.get("time")
    if not cached_time:
        return False
    try:
        cached_dt = datetime.strptime(cached_time, "%Y-%m-%d %H:%M:%S")
        return datetime.now() - cached_dt < timedelta(hours=max_hours)
    except (ValueError, TypeError):
        return False


def _send_to_user(state, user_id, text):
    """向指定用户发送消息（使用缓存的 context_token）"""
    cached = state.get("cached_tokens", {})
    info = cached.get(user_id)
    if info:
        if not _is_token_fresh(info):
            print(f"  主动发送→{user_id[:15]}: 跳过（token 已超 20h，等用户下次发消息刷新）")
            return False
        ok = send_message(state, user_id, info["context_token"], text)
        print(f"  主动发送→{user_id[:15]}: {'✓' if ok else '✗'}")
        return ok
    return False


def _resolve_image_path(image_key, species_id="penguin"):
    """解析图片路径，支持变体随机选择。
    有变体时从 {key}.png + {key}_1.png, {key}_2.png... 全部候选中随机选。
    """
    import glob
    assets_dir = _get_assets_dir(species_id)
    single = os.path.join(assets_dir, f"{image_key}.png")
    variants = glob.glob(os.path.join(assets_dir, f"{image_key}_*.png"))
    if variants:
        candidates = variants[:]
        if os.path.exists(single):
            candidates.append(single)
        return random.choice(candidates)
    if os.path.exists(single):
        return single
    return None


def _send_image_by_key(state, user_id, context_token, image_key, species_id="penguin"):
    """根据 image_key 发送对应的素材图片（支持变体随机）"""
    img_path = _resolve_image_path(image_key, species_id)
    if not img_path:
        print(f"  素材不存在: {image_key}")
        return False
    try:
        from image import send_image_file
        return send_image_file(state, user_id, context_token, img_path)
    except Exception as e:
        print(f"  发送图片失败: {e}")
        return False


# ============================================================
# 主循环
# ============================================================
def run_loop(state, on_message=None):
    """
    主轮询循环。
    on_message(user_id, text, is_voice) → reply_text
    """
    cursor = state.get("cursor", "")
    processed_seqs = set()

    print("  等待消息...（Ctrl+C 退出）\n")

    try:
        while True:
            body = {
                "get_updates_buf": cursor,
                "base_info": {"channel_version": "1.0.0"},
                "longpolling_timeout_ms": 3000,
            }
            resp = _api_request("POST", "/ilink/bot/getupdates",
                                body=body, headers=_make_headers(state["bot_token"]), timeout=5)

            if not resp or resp.get("timeout"):
                continue
            if "error" in resp or "_ret_error" in resp:
                ret_val = resp.get("_ret_error") or resp.get("ret")
                if ret_val == -14:
                    print("  Session 过期，需要重新登录")
                    return
                time.sleep(2)
                continue

            new_cursor = resp.get("get_updates_buf", cursor)
            if new_cursor != cursor:
                cursor = new_cursor
                state["cursor"] = cursor
                save_state(state)

            for msg in resp.get("msgs", []):
                seq = msg.get("seq") or msg.get("message_id", "")
                if seq and seq in processed_seqs:
                    continue
                if seq:
                    processed_seqs.add(seq)
                    if len(processed_seqs) > 200:
                        processed_seqs.clear()

                user_id = msg.get("from_user_id", "")
                context_token = msg.get("context_token", "")

                state.setdefault("cached_tokens", {})[user_id] = {
                    "context_token": context_token,
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                save_state(state)

                for item in msg.get("item_list", []):
                    item_type = item.get("type", 0)
                    text = None
                    is_voice = False

                    if item_type == 1:
                        text = item.get("text_item", {}).get("text", "")
                    elif item_type == 3:
                        text = item.get("voice_item", {}).get("text", "")
                        is_voice = True
                        if not text:
                            send_message(state, user_id, context_token, "语音没听清呢，试试发文字？")
                            continue

                    if not text:
                        continue

                    v = "🎤" if is_voice else ""
                    print(f"\n  收到{v}: {text[:50]}")

                    if on_message:
                        reply = on_message(user_id, text, is_voice)
                        if reply:
                            # 支持 (text, image_key, species_id) / (text, image_key) / str
                            if isinstance(reply, str):
                                reply_text, image_key, species_id = reply, None, "penguin"
                            elif len(reply) == 3:
                                reply_text, image_key, species_id = reply
                            else:
                                reply_text, image_key = reply
                                species_id = "penguin"
                            ok = send_message(state, user_id, context_token, reply_text)
                            print(f"  回复: {reply_text[:60]}{'...' if len(reply_text)>60 else ''}")
                            print(f"  {'✓' if ok else '✗'}")
                            if image_key:
                                _send_image_by_key(state, user_id, context_token, image_key, species_id)

    except KeyboardInterrupt:
        print("\n\n  宠物已休息 👋")


# ============================================================
# 启动入口
# ============================================================
def start():
    """正式启动：APScheduler 管调度，轮询只管收发消息"""
    import atexit
    from apscheduler.schedulers.background import BackgroundScheduler
    from config import DATA_DIR
    from store import PetRegistry
    from core import MessageHandler
    from scheduler import create_scheduler

    registry = PetRegistry(str(DATA_DIR))
    handler = MessageHandler(registry=registry)
    state = load_state()

    if not state.get("bot_token"):
        print("  未登录，先登录...")
        state = login()
        if not state:
            print("  登录失败")
            return

    def send_fn(user_id, text):
        _send_to_user(state, user_id, text)

    def send_image_fn(user_id, image_key, species_id="penguin"):
        cached = state.get("cached_tokens", {})
        info = cached.get(user_id)
        if info and _is_token_fresh(info):
            _send_image_by_key(state, user_id, info["context_token"], image_key, species_id)

    scheduler = create_scheduler(registry, send_fn, send_image_fn)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown(wait=False))

    from config import AI_API_KEY, AI_BASE_URL
    if not AI_API_KEY or AI_API_KEY in ("your_api_key", "your_deepseek_api_key_here"):
        print("\n  ⚠️  AI_API_KEY 未配置！宠物基础互动正常，但 AI 闲聊/日记/周报不可用。")
        print("     请在 pet/.env 中设置你的 API Key。")
    if not AI_BASE_URL:
        print("\n  ⚠️  AI_BASE_URL 未配置！AI 功能不可用。")

    active = registry.all_active_stores()
    print(f"\n=== 017Pet V2 已启动 ===")
    print(f"  已注册用户: {len(active)}")
    print(f"  状态衰减: 每{DECAY_INTERVAL_MIN}分钟")
    print(f"  调度器: APScheduler")

    def on_message(user_id, text, is_voice):
        try:
            from scheduler import mark_user_interaction
            mark_user_interaction(user_id)
            reply = handler.handle_message(user_id, text, is_voice)
            # 如果回复包含图片 key，获取用户品种用于素材路径
            if isinstance(reply, tuple) and len(reply) == 2:
                text_reply, image_key = reply
                user_store = registry.get_or_create(user_id)
                species_id = user_store.get_species_id() or "penguin"
                # 返回 3 元组让 run_loop 里的发送逻辑知道品种
                return (text_reply, image_key, species_id)
            return reply
        except Exception as e:
            print(f"  处理异常: {e}")
            import traceback
            traceback.print_exc()
            return "出了点问题... (>_<)"

    run_loop(state, on_message=on_message)


# ============================================================
# CLI 入口
# ============================================================
def main():
    state = load_state()

    if len(sys.argv) < 2:
        print("用法: py ilink.py <start|login|status|send TEXT|send-image [PATH]>")
        return

    cmd = sys.argv[1]

    if cmd == "start":
        start()
    elif cmd == "login":
        login()
    elif cmd == "status":
        if state.get("bot_token"):
            print(f"  已登录 ({state.get('login_time', '?')})")
            print(f"  bot_id: {state.get('bot_id', '?')}")
            cached = state.get("cached_tokens", {})
            print(f"  缓存 token: {len(cached)} 个用户")
        else:
            print("  未登录")
    elif cmd == "send" and len(sys.argv) >= 3:
        text = " ".join(sys.argv[2:])
        cached = state.get("cached_tokens", {})
        for uid, info in cached.items():
            ok = send_message(state, uid, info["context_token"], text)
            print(f"  → {uid[:20]}: {'✓' if ok else '✗'}")
            break
    elif cmd == "send-image":
        from image import send_image_file
        img_path = sys.argv[2] if len(sys.argv) >= 3 else "test_image.png"
        if not os.path.exists(img_path):
            print(f"  图片不存在: {img_path}")
            return
        cached = state.get("cached_tokens", {})
        if not cached:
            print("  没有缓存的用户 token，先在微信给 bot 发一条消息")
            return
        for uid, info in cached.items():
            print(f"  发送图片到 {uid[:20]}...")
            ok = send_image_file(state, uid, info["context_token"], img_path)
            print(f"  结果: {'✓ 成功' if ok else '✗ 失败'}")
            break
    else:
        print(f"  未知命令: {cmd}")


if __name__ == "__main__":
    main()
