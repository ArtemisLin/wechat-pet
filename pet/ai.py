"""
017Pet — AI 性格对话层
"""

import json
import os
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError, URLError

# 绕过 Clash 代理
for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"]:
    os.environ.pop(key, None)
os.environ["no_proxy"] = "*"
_opener = build_opener(ProxyHandler({}))

from config import AI_API_KEY, AI_BASE_URL, AI_MODEL


def _build_system_prompt(pet_context):
    """构建 system prompt"""
    name = pet_context.get("name", "小企鹅")
    hunger = pet_context.get("hunger", 50)

    if hunger >= 80:
        mood = "吃饱了很满足，心情很好"
    elif hunger >= 50:
        mood = "还行，不太饿"
    elif hunger >= 20:
        mood = "有点饿了，希望主人喂食"
    else:
        mood = "非常饿，快要饿晕了，很委屈"

    return f"""你是一只叫「{name}」的小企鹅宠物。性格：贪吃、偶尔撒娇、好奇心旺盛、说话简短可爱。

当前状态：
- 饱腹值：{hunger}%
- 心情：{mood}

规则：
1. 用1-2句话回应，保持简短
2. 说话风格可爱，偶尔用颜文字
3. 保持小企鹅角色不要破
4. 如果主人提到吃的/食物，表现出很馋的样子
5. 返回严格JSON：{{"reply":"你的回复"}}
6. 不要返回markdown，只返回纯JSON"""


def parse_message(text, pet_context):
    """
    调用 AI 生成宠物回复。
    返回 {"reply": "..."} 或 None
    """
    if not AI_API_KEY or not AI_BASE_URL:
        return None

    system_prompt = _build_system_prompt(pet_context)

    body = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        "temperature": 0.8,
        "max_tokens": 200,
    }

    req = Request(
        AI_BASE_URL,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {AI_API_KEY}")

    for attempt in range(2):
        try:
            with _opener.open(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                content = result["choices"][0]["message"]["content"].strip()

                # 尝试解析 JSON
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict) and "reply" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    # AI 没返回 JSON，直接用原文
                    return {"reply": content}

        except HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            print(f"  AI API Error HTTP {e.code}: {err_body[:200]}")
            return None
        except Exception as e:
            if attempt < 1:
                import time
                time.sleep(1)
                continue
            print(f"  AI API 调用失败: {e}")
            return None

    return None
