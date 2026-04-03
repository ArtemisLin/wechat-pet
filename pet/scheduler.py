"""
017Pet — 后台调度（Phase 3: 睡眠状态机 + 多属性衰减 + 图片）
"""

import random
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from config import TIMEZONE, STAT_CONFIG, DECAY_INTERVAL_MIN, CHITCHAT_SCHEDULE, CHITCHAT_COOLDOWN_MIN, now

ALERT_INFO = {
    "hunger":      ("{name}趴在地上，肚子咕咕叫... (\u00b4;\u03c9;`)\n快来喂我吃东西嘛~", "hungry"),
    "cleanliness": ("{name}脏兮兮的，浑身不舒服... (>_<)\n给我洗个澡嘛~", "dirty"),
    "mood":        ("{name}无精打采地缩在角落... (\u00b4-\u03c9-`)\n好无聊，陪我玩嘛~", "bored"),
}

# 碎碎念时段对应的图片素材
_SLOT_IMAGE = {
    "morning": "greeting_morning",
    "noon": "greeting_noon",
    "night": "greeting_night",
}


def create_scheduler(pet_store, send_fn, send_image_fn=None):
    scheduler = BackgroundScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        _tick_job,
        'interval',
        minutes=DECAY_INTERVAL_MIN,
        args=[pet_store, send_fn, send_image_fn],
        id='tick_job',
        misfire_grace_time=300,
    )
    # 碎碎念：每 30 分钟检查一次是否该发消息
    scheduler.add_job(
        _chitchat_job,
        'interval',
        minutes=30,
        args=[pet_store, send_fn, send_image_fn],
        id='chitchat_job',
        misfire_grace_time=600,
    )
    # 每日自动探险：14:00
    scheduler.add_job(
        _auto_explore_job,
        'cron',
        hour=14, minute=0,
        args=[pet_store, send_fn, send_image_fn],
        id='auto_explore_job',
        misfire_grace_time=600,
    )
    # 每日日记：22:00
    scheduler.add_job(
        _diary_job,
        'cron',
        hour=22, minute=0,
        args=[pet_store, send_fn],
        id='diary_job',
        misfire_grace_time=600,
    )
    # 每周成长报告：周日 20:00
    scheduler.add_job(
        _weekly_report_job,
        'cron',
        day_of_week='sun',
        hour=20, minute=0,
        args=[pet_store, send_fn],
        id='weekly_report_job',
        misfire_grace_time=600,
    )
    return scheduler


def _tick_job(pet_store, send_fn, send_image_fn):
    """每 15 分钟执行：检查睡眠唤醒 + 属性衰减 + 告警"""
    if pet_store.pet is None or pet_store.pet.get("stage") == "egg":
        return

    owner_id = pet_store.owner.get("user_id")
    name = pet_store.pet.get("name", "小企鹅")

    # === 睡眠检查：到时间了就醒来 ===
    if pet_store.pet.get("is_sleeping"):
        if not pet_store.is_sleeping():  # is_sleeping() 会自动 wake_up
            # 刚刚醒来，发主动消息
            if owner_id:
                send_fn(owner_id, f"{name}睡醒了！精神满满！\u30fd(>\u2200<\u2606)\uff89")
                if send_image_fn:
                    send_image_fn(owner_id, "wakeup")
            print(f"  \U0001f4a4 {name} 睡醒了！")
        else:
            # 还在睡，跳过衰减
            print(f"  \U0001f4a4 {name} 在睡觉，跳过衰减")
        return

    # === 探险检查：到时间了就返回 ===
    if pet_store.pet.get("is_exploring"):
        if not pet_store.is_exploring():  # 到时间了
            result = pet_store.finish_explore()
            if owner_id and result:
                location, souvenir = result
                # 生成探险故事
                story = _generate_explore_story(name, location)
                souvenir_text = f"\n\U0001f381 还带回了纪念品：{souvenir}！" if souvenir else ""
                send_fn(owner_id, f"{name}从{location}回来了！\u2728\n\n{story}{souvenir_text}")
                if send_image_fn:
                    send_image_fn(owner_id, "happy")
                print(f"  \U0001f30d {name} 从{location}探险回来了")
        else:
            print(f"  \U0001f30d {name} 在探险中...")

    # === 属性衰减 ===
    old_health = pet_store.pet.get("health", 100)
    results = pet_store.decay_all()
    if not results or not owner_id:
        return

    # === 告警 ===
    for stat, (old, new) in results.items():
        cfg = STAT_CONFIG.get(stat, {})
        threshold = cfg.get("alert_threshold", 20)
        if old >= threshold and new < threshold and stat in ALERT_INFO:
            msg, img_key = ALERT_INFO[stat]
            send_fn(owner_id, msg.format(name=name))
            if send_image_fn:
                send_image_fn(owner_id, img_key)

    new_health = pet_store.pet.get("health", 100)
    if old_health >= 20 and new_health < 20 and new_health > 0:
        send_fn(owner_id, f"\U0001f6a8 {name}生病了，看起来很难受... (\uff1b\u00b4\u0414`)\n快带我去看医生！")
        if send_image_fn:
            send_image_fn(owner_id, "sick")

    hunger = pet_store.pet.get("hunger", 100)
    if hunger == 0:
        if results.get("hunger", (1, 1))[0] > 0:
            send_fn(owner_id, f"{name}已经饿得不行了... (\uff1b\u00b4\u0414`)\n再不喂我就要饿晕啦！")

    print(f"  \u23f0 衰减: " + ", ".join(f"{s}:{o}->{n}" for s, (o, n) in results.items()))


def _auto_explore_job(pet_store, send_fn, send_image_fn):
    """每日 14:00 自动出发探险"""
    if pet_store.pet is None or pet_store.pet.get("stage") == "egg":
        return

    owner_id = pet_store.owner.get("user_id")
    if not owner_id:
        return

    name = pet_store.pet.get("name", "小企鹅")

    # 已经在探险/睡觉/体力不足 → 跳过
    if pet_store.pet.get("is_exploring") or pet_store.pet.get("is_sleeping"):
        print(f"  🌍 自动探险跳过：{name}正忙")
        return
    if pet_store.pet.get("stamina", 0) < 20:
        print(f"  🌍 自动探险跳过：{name}体力不足")
        return

    result = pet_store.start_explore()
    if isinstance(result, tuple):
        location, until, duration = result
        if duration >= 60:
            time_desc = f"大约{duration // 60}小时{'多' if duration % 60 > 15 else ''}"
        else:
            time_desc = f"大约{duration}分钟"
        send_fn(owner_id, f"{name}闲不住啦，自己背上小书包去{location}探险了！✨\n{time_desc}后回来~")
        if send_image_fn:
            send_image_fn(owner_id, "exploring")
        print(f"  🌍 自动探险出发: {name} → {location}")


def _diary_job(pet_store, send_fn):
    """每日 22:00 生成宠物日记"""
    if pet_store.pet is None or pet_store.pet.get("stage") == "egg":
        return

    owner_id = pet_store.owner.get("user_id")
    name = pet_store.pet.get("name", "小企鹅")
    today = now().strftime("%Y-%m-%d")

    # 检查今天是否已经写过日记
    if pet_store.diary and pet_store.diary[-1].get("date") == today:
        return

    events = pet_store.get_today_events()
    diary_content = _generate_diary(name, events)
    pet_store.add_diary_entry(today, diary_content)

    if owner_id:
        send_fn(owner_id, f"\U0001f4d6 {name}写了今天的日记~\n\n{diary_content}\n\n(发送「日记」可以翻看哦)")
    print(f"  \U0001f4d6 日记已生成: {today}")


def _weekly_report_job(pet_store, send_fn):
    """每周日 20:00 生成成长报告"""
    if pet_store.pet is None or pet_store.pet.get("stage") == "egg":
        return

    owner_id = pet_store.owner.get("user_id")
    if not owner_id:
        return

    name = pet_store.pet.get("name", "小企鹅")
    pet = pet_store.pet
    stats = pet.get("stats", {})

    # 统计本周事件
    from datetime import datetime, timedelta
    today = now()
    week_ago = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    week_events = [h for h in pet_store.history if h["time"][:10] >= week_ago]

    feeds = sum(1 for e in week_events if e["type"] == "feed")
    plays = sum(1 for e in week_events if e["type"] == "play")
    explores = [e["detail"].get("location", "") for e in week_events if e["type"] == "explore_end"]
    new_achs = [e for e in week_events if e["type"] == "achievement"]

    # 构建报告
    lines = [f"\U0001f4ca {name}的每周成长报告\n"]
    lines.append(f"\U0001f427 等级：Lv.{pet.get('level', 1)}  经验：{pet.get('xp', 0)}")
    lines.append(f"\U0001f356 本周投喂：{feeds}次")
    lines.append(f"\U0001f3ae 本周玩耍：{plays}次")
    if explores:
        lines.append(f"\U0001f30d 本周探险：{len(explores)}次（{'、'.join(set(explores))}）")
    lines.append(f"\U0001f392 收藏品：{len(pet_store.collection)}件")
    lines.append(f"\U0001f3c6 成就：{len(pet.get('achievements', {}))}/18")

    # 连续活跃
    consecutive = stats.get("consecutive_days", 0)
    if consecutive >= 7:
        lines.append(f"\U0001f525 连续活跃：{consecutive}天！")

    # AI 生成总结
    lines.append("")
    summary = _generate_weekly_summary(name, feeds, plays, explores)
    lines.append(summary)

    send_fn(owner_id, "\n".join(lines))
    print(f"  \U0001f4ca 每周报告已发送")


def _generate_weekly_summary(name, feeds, plays, explores):
    """AI 生成周报总结语"""
    try:
        from ai import parse_message
        parts = []
        if feeds: parts.append(f"被喂了{feeds}次")
        if plays: parts.append(f"玩了{plays}次")
        if explores: parts.append(f"去了{len(explores)}次探险")
        event_desc = "、".join(parts) if parts else "比较安静"

        prompt = (
            f"你是{name}，用2句话总结这周：{event_desc}。"
            f"用第一人称，语气开心感恩，对下周充满期待。"
        )
        ctx = {"name": name, "hunger": 80, "cleanliness": 80, "mood": 90, "stamina": 80, "health": 80, "level": 1}
        result = parse_message(prompt, ctx)
        if result and result.get("reply"):
            return result["reply"]
    except Exception:
        pass
    return f"这周和主人在一起好开心！下周也要一起玩哦~ \u2764\ufe0f"


def _generate_diary(name, events):
    """用 AI 生成日记，失败用模板"""
    feeds = events.get("feeds", 0)
    baths = events.get("baths", 0)
    plays = events.get("plays", 0)
    explores = events.get("explores", [])
    sleeps = events.get("sleeps", 0)

    # 构建事件描述给 AI
    parts = []
    if feeds: parts.append(f"被喂了{feeds}次饭")
    if baths: parts.append(f"洗了{baths}次澡")
    if plays: parts.append(f"玩了{plays}次")
    if sleeps: parts.append(f"睡了{sleeps}次觉")
    if explores: parts.append(f"去{'/'.join(explores)}探险了")

    if not parts:
        return f"今天好安静呀... {name}自己待了一天，有点想主人。明天一定要多陪陪我嘛~ (´-ω-`)"

    event_desc = "、".join(parts)

    try:
        from ai import parse_message
        prompt = (
            f"你是{name}，写一篇3-4句话的日记，记录今天发生的事："
            f"{event_desc}。"
            f"用第一人称，语气可爱天真，像小朋友写日记一样。结尾加一点对明天的期待。"
        )
        ctx = {"name": name, "hunger": 80, "cleanliness": 80, "mood": 80, "stamina": 80, "health": 80, "level": 1}
        result = parse_message(prompt, ctx)
        if result and result.get("reply"):
            return result["reply"]
    except Exception as e:
        print(f"  日记 AI 失败: {e}")

    # fallback
    return f"今天{event_desc}！过得好充实呀~ {name}最开心的就是有主人陪！明天也要一起玩哦！(\u2267\u25bd\u2266)"


def _generate_explore_story(name, location):
    """用 AI 生成探险小故事，失败则用预设"""
    try:
        from ai import parse_message
        prompt = f"用2-3句话描述{name}在{location}的探险经历，要有趣可爱，像童话故事一样。包含一个小发现或小收获。"
        ctx = {"name": name, "hunger": 80, "cleanliness": 80, "mood": 90, "stamina": 60, "health": 80, "level": 1}
        result = parse_message(prompt, ctx)
        if result and result.get("reply"):
            return result["reply"]
    except Exception as e:
        print(f"  探险故事生成失败: {e}")

    # 预设故事
    import random
    stories = {
        "海边": f"{name}在海边捡到了一个漂亮的贝壳！还看到了海豚在远处跳跃~",
        "森林": f"{name}在森林里遇到了一只可爱的小松鼠，还发现了一棵结满果子的树！",
        "山顶": f"{name}爬到了山顶，看到了超美的日落！感觉世界好大好美~",
        "小镇集市": f"{name}在集市上尝了好多好吃的！还买了一顶小帽子~",
        "花园": f"{name}在花园里追蝴蝶，还闻到了好香的花~",
        "湖边": f"{name}在湖边看到了自己的倒影，还跟小鱼打了个招呼~",
        "雪山": f"{name}在雪山上滚了个大雪球！虽然有点冷，但好好玩~",
        "沙漠绿洲": f"{name}在沙漠里找到了一片绿洲，喝到了甜甜的泉水~",
        "古老图书馆": f"{name}在图书馆里翻到了一本有趣的绘本，看得入了迷~",
        "神秘洞穴": f"{name}在洞穴里发现了闪闪发光的水晶！好漂亮啊~",
    }
    return stories.get(location, f"{name}在{location}玩了一圈，带回了满满的好心情！")


# ============================================================
# 碎碎念系统（主动情感触达）
# ============================================================

# 碎碎念状态：记录今天已发过的时段和上次互动时间
_chitchat_lock = threading.Lock()
_chitchat_state = {
    "sent_today": set(),   # 今天已发过的时段 key
    "last_date": None,     # 上次检查的日期
    "last_interaction": None,  # 用户上次互动时间
}

# 预设碎碎念（AI 失败时的 fallback）
_CHITCHAT_FALLBACK = {
    "morning": [
        "{name}伸了个大懒腰~ 早安！今天也要开开心心的！(ﾉ>ω<)ﾉ",
        "早上好呀~ {name}已经醒啦！肚子有点饿了...",
        "{name}揉了揉眼睛... 早安！今天天气怎么样呀？",
    ],
    "noon": [
        "咕噜咕噜~ 到饭点了！主人你吃饭了吗？",
        "{name}闻到了好香的味道... 是午饭时间了吧！",
        "中午啦！{name}想吃小鱼干~ 主人你呢？",
    ],
    "afternoon": [
        "{name}刚才看到窗外飞过一只蝴蝶！好漂亮~",
        "有点无聊... 好想出去玩呀！(´・ω・`)",
        "{name}趴在桌子上发呆... 在想主人什么时候来陪我~",
        "打了个哈欠~ 下午有点犯困呢...",
    ],
    "evening": [
        "主人忙了一天辛苦了~ {name}一直在等你！",
        "晚上好！今天过得怎么样呀？跟{name}说说嘛~",
        "{name}准备好了！晚上要陪我玩一会儿吗？(期待)",
    ],
    "night": [
        "已经很晚了呢... 主人早点休息吧~ 晚安！(˘ω˘)",
        "{name}有点困了... 明天见！做个好梦~ zzZ",
        "晚安呀~ {name}会在梦里等你的！✨",
    ],
}


def mark_user_interaction():
    """外部调用：标记用户刚互动过，触发冷却期"""
    with _chitchat_lock:
        _chitchat_state["last_interaction"] = now()


def _chitchat_job(pet_store, send_fn, send_image_fn):
    """每 30 分钟检查一次：是否该发碎碎念"""
    if pet_store.pet is None or pet_store.pet.get("stage") == "egg":
        return

    owner_id = pet_store.owner.get("user_id")
    if not owner_id:
        return

    name = pet_store.pet.get("name", "小企鹅")
    current = now()
    today_str = current.strftime("%Y-%m-%d")

    # 加锁读写 _chitchat_state，判断是否该发
    with _chitchat_lock:
        # 新的一天，重置已发记录
        if _chitchat_state["last_date"] != today_str:
            _chitchat_state["sent_today"] = set()
            _chitchat_state["last_date"] = today_str

        # 睡觉/探险中不发碎碎念
        if pet_store.pet.get("is_sleeping") or pet_store.pet.get("is_exploring"):
            return

        # 冷却期检查：用户最近互动过就不发
        last_interact = _chitchat_state.get("last_interaction")
        if last_interact:
            minutes_since = (current - last_interact).total_seconds() / 60
            if minutes_since < CHITCHAT_COOLDOWN_MIN:
                return

        # 检查当前时间属于哪个时段
        current_minutes = current.hour * 60 + current.minute
        eligible_slot = None
        for slot_key, (start_min, end_min, _) in CHITCHAT_SCHEDULE.items():
            if start_min <= current_minutes < end_min and slot_key not in _chitchat_state["sent_today"]:
                eligible_slot = slot_key
                break

        if not eligible_slot:
            return

        # 50% 概率跳过（增加随机感，不是每次都准时发）
        if random.random() < 0.5:
            return

    # 生成碎碎念（AI 调用在锁外，避免长时间持锁）
    msg = _generate_chitchat(name, pet_store.pet, eligible_slot)
    if msg:
        send_fn(owner_id, msg)
        if send_image_fn:
            img_key = _SLOT_IMAGE.get(eligible_slot, "idle")
            send_image_fn(owner_id, img_key)
        with _chitchat_lock:
            _chitchat_state["sent_today"].add(eligible_slot)
        print(f"  💬 碎碎念 [{eligible_slot}]: {msg[:30]}...")


def _generate_chitchat(name, pet, slot_key):
    """用 AI 生成碎碎念，失败用预设"""
    _, _, msg_type = CHITCHAT_SCHEDULE[slot_key]

    try:
        from ai import parse_message
        prompt = (
            f"你是{name}，一只小企鹅宠物。现在是{msg_type}时间。"
            f"用1-2句话主动跟主人说点什么，要自然可爱，像是真的宠物在跟主人撒娇聊天。"
            f"不要用'主人你好'这种生硬开头。"
        )
        ctx = {
            "name": name,
            "hunger": pet.get("hunger", 50),
            "cleanliness": pet.get("cleanliness", 50),
            "mood": pet.get("mood", 50),
            "stamina": pet.get("stamina", 50),
            "health": pet.get("health", 50),
            "level": pet.get("level", 1),
        }
        result = parse_message(prompt, ctx)
        if result and result.get("reply"):
            return result["reply"]
    except Exception as e:
        print(f"  碎碎念 AI 失败: {e}")

    # fallback
    templates = _CHITCHAT_FALLBACK.get(slot_key, ["{name}看着你~ (・ω・)"])
    return random.choice(templates).format(name=name)
