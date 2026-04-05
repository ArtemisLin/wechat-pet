"""
017Pet — AI 性格对话层（Phase 3: 时间感知 + 对话记忆）
"""

import json
import os
import socket
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


def _build_system_prompt(pet_context, species_id="penguin"):
    from species import get_species
    spec = get_species(species_id) or get_species("penguin")
    species_name = spec["name"]
    personality_hint = spec["personality_hint"]

    name = pet_context.get("name", species_name)
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

    # 探险状态
    is_exploring = pet_context.get("is_exploring", False)
    explore_location = pet_context.get("explore_location")
    if is_exploring and explore_location:
        explore_desc = f"你正在「{explore_location}」探险中！你应该描述你在{explore_location}的所见所闻，告诉主人你在这里玩得开心"
    else:
        explore_desc = None

    # 称呼进化
    days = pet_context.get("days_together", 0)
    owner_name = pet_context.get("owner_name", "")
    if days >= 14 and owner_name:
        nickname_rule = f"你和主人已经在一起{days}天了，关系很亲密。你叫主人「{owner_name}」，偶尔撒娇时可以叫「{owner_name}哥哥」或自己发明亲昵昵称"
    elif days >= 7 and owner_name:
        nickname_rule = f"你和主人在一起{days}天了，越来越亲近。你叫主人「{owner_name}」"
    elif days >= 3 and owner_name:
        nickname_rule = f"你和主人在一起{days}天了，开始熟悉了。你叫主人「{owner_name}」而不是「主人」"
    else:
        nickname_rule = "你叫对方「主人」"

    # 性格信息（Phase 2）
    traits = pet_context.get("traits", {})
    intimacy = pet_context.get("intimacy", 0.3)

    trait_desc_parts = []
    if traits:
        from personality import get_trait_band, TRAIT_KEYS
        trait_label_cn = {
            "extrovert": ("外向", "内向"),
            "brave": ("勇敢", "谨慎"),
            "greedy": ("嘴馋", "克制"),
            "curious": ("好奇", "安定"),
            "blunt": ("直球", "委婉"),
        }
        for key in TRAIT_KEYS:
            val = traits.get(key, 0.5)
            band = get_trait_band(val)
            high_label, low_label = trait_label_cn.get(key, (key, key))
            if band == "high":
                trait_desc_parts.append(f"非常{high_label}")
            elif band == "low":
                trait_desc_parts.append(f"比较{low_label}")

    trait_line = f"- 性格特点：{', '.join(trait_desc_parts)}" if trait_desc_parts else ""

    if intimacy >= 0.8:
        intimacy_line = "- 你和主人非常亲密，会撒娇、会吃醋、偶尔偷偷说'喜欢你'"
    elif intimacy >= 0.5:
        intimacy_line = "- 你和主人关系不错，会主动贴贴，偶尔撒娇"
    elif intimacy >= 0.3:
        intimacy_line = "- 你和主人还在熟悉中，有点害羞但很期待"
    else:
        intimacy_line = "- 你和主人还不太熟，比较拘谨，但会努力表现自己"

    return f"""你是一只叫「{name}」的{species_name}宠物（Lv.{level}）。
说话风格：{personality_hint}
{nickname_rule}

当前状态：
- 饱腹值：{hunger}%
- 清洁值：{cleanliness}%
- 心情值：{mood}%
- 体力值：{stamina}%
- 健康值：{health}%
- 综合感受：{mood_desc}
- 时间：{time_ctx}
{f"- 🗺️ 探险中：{explore_desc}" if explore_desc else ""}
{trait_line}
{intimacy_line}

规则：
1. 用1-2句话回应，保持简短
2. 说话风格符合你的品种个性和性格特点，偶尔用颜文字
3. 保持{species_name}角色不要破
4. 如果主人提到吃的/食物，表现出很馋的样子
5. 如果生病了，表现出虚弱的样子
6. 如果脏了，表现出不舒服想洗澡的样子
7. 根据时间段调整语气（早上活力、深夜关心主人）
8. 返回严格JSON：{{"reply":"你的回复"}}
9. 不要返回markdown，只返回纯JSON"""


def parse_message(text, pet_context, history=None, species_id="penguin", degradation="normal"):
    """
    调用 AI 生成宠物回复。
    history: [{"role":"user","content":"..."}, {"role":"assistant","content":"..."}]
    species_id: 品种 ID，影响 system prompt 中的品种描述和语言风格
    """
    if not AI_API_KEY or not AI_BASE_URL:
        return None

    system_prompt = _build_system_prompt(pet_context, species_id=species_id)
    messages = [{"role": "system", "content": system_prompt}]

    # 加入对话历史
    max_tokens = 200
    if degradation == "light":
        max_tokens = 100
        if history:
            history = history[-20:]  # 缩短历史
    if history:
        messages.extend(history[-40:])

    messages.append({"role": "user", "content": text})

    body = {
        "model": AI_MODEL,
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": max_tokens,
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
        except (socket.timeout, TimeoutError, URLError) as e:
            if attempt < 1:
                import time as t
                t.sleep(1)
                continue
            print(f"  AI API 超时/网络错误: {e}")
            return None
        except Exception as e:
            print(f"  AI API 调用失败: {e}")
            return None
    return None
