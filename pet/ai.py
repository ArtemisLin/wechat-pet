"""
017Pet — AI 性格对话层（Phase 3: 时间感知 + 对话记忆）
"""

import json
import os
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError, URLError

for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"]:
    os.environ.pop(key, None)
os.environ["no_proxy"] = "*"
_opener = build_opener(ProxyHandler({}))

from config import AI_API_KEY, AI_BASE_URL, AI_MODEL, now


def _get_time_context():
    """根据当前时间返回时间段描述"""
    hour = now().hour
    if 6 <= hour < 9:
        return "现在是早晨，主人刚起床，适合说早安、问候"
    elif 9 <= hour < 12:
        return "现在是上午"
    elif 12 <= hour < 14:
        return "现在是午饭时间，可以提醒主人吃饭"
    elif 14 <= hour < 18:
        return "现在是下午"
    elif 18 <= hour < 21:
        return "现在是晚上"
    elif 21 <= hour < 24:
        return "现在是深夜了，可以跟主人说晚安，提醒早点休息"
    else:
        return "现在是凌晨，主人还没睡！应该关心主人为什么这么晚还没睡"


def _build_system_prompt(pet_context):
    name = pet_context.get("name", "小企鹅")
    hunger = pet_context.get("hunger", 50)
    cleanliness = pet_context.get("cleanliness", 50)
    mood = pet_context.get("mood", 50)
    stamina = pet_context.get("stamina", 50)
    health = pet_context.get("health", 50)
    level = pet_context.get("level", 1)

    moods = []
    if hunger < 20: moods.append("非常饿")
    elif hunger < 50: moods.append("有点饿")
    if cleanliness < 20: moods.append("浑身脏兮兮很不舒服")
    elif cleanliness < 50: moods.append("有点脏")
    if mood < 20: moods.append("很无聊很沮丧")
    elif mood < 50: moods.append("有点无聊")
    if stamina < 20: moods.append("非常疲惫")
    if health < 20: moods.append("生病了，很虚弱")

    if not moods:
        if min(hunger, cleanliness, mood, stamina, health) >= 80:
            mood_desc = "状态非常好，特别开心活泼"
        else:
            mood_desc = "状态还不错"
    else:
        mood_desc = "、".join(moods)

    time_ctx = _get_time_context()

    return f"""你是一只叫「{name}」的小企鹅宠物（Lv.{level}）。你现在的名字就是「{name}」，即使对话历史中出现过其他名字，你也必须只用「{name}」自称。性格：贪吃、偶尔撒娇、好奇心旺盛、说话简短可爱。

当前状态：
- 饱腹值：{hunger}%
- 清洁值：{cleanliness}%
- 心情值：{mood}%
- 体力值：{stamina}%
- 健康值：{health}%
- 综合感受：{mood_desc}
- 时间：{time_ctx}

规则：
1. 用1-2句话回应，保持简短
2. 说话风格可爱，偶尔用颜文字
3. 保持小企鹅角色不要破
4. 如果主人提到吃的/食物，表现出很馋的样子
5. 如果生病了，表现出虚弱的样子
6. 如果脏了，表现出不舒服想洗澡的样子
7. 根据时间段调整语气（早上活力、深夜关心主人）
8. 返回严格JSON：{{"reply":"你的回复"}}
9. 不要返回markdown，只返回纯JSON"""


def parse_message(text, pet_context, history=None):
    """
    调用 AI 生成宠物回复。
    history: [{"role":"user","content":"..."}, {"role":"assistant","content":"..."}]
    """
    if not AI_API_KEY or not AI_BASE_URL:
        return None

    system_prompt = _build_system_prompt(pet_context)
    messages = [{"role": "system", "content": system_prompt}]

    # 加入对话历史
    if history:
        messages.extend(history[-40:])  # 最近 20 轮

    messages.append({"role": "user", "content": text})

    body = {
        "model": AI_MODEL,
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": 200,
    }

    req = Request(AI_BASE_URL, data=json.dumps(body).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {AI_API_KEY}")

    for attempt in range(2):
        try:
            with _opener.open(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                content = result["choices"][0]["message"]["content"].strip()
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict) and "reply" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    return {"reply": content}
        except HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            print(f"  AI API Error HTTP {e.code}: {err_body[:200]}")
            return None
        except Exception as e:
            if attempt < 1:
                import time as t
                t.sleep(1)
                continue
            print(f"  AI API 调用失败: {e}")
            return None
    return None
