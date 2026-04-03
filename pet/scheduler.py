"""
017Pet — 后台调度（V2: 多用户支持）
"""

import random
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from config import TIMEZONE, STAT_CONFIG, DECAY_INTERVAL_MIN, CHITCHAT_SCHEDULE, CHITCHAT_COOLDOWN_MIN, now

ALERT_INFO = {
    "hunger":      ("{name}趴在地上，肚子咕咕叫... (´;ω;`)\n快来喂我吃东西嘛~", "hungry"),
    "cleanliness": ("{name}脏兮兮的，浑身不舒服... (>_<)\n给我洗个澡嘛~", "dirty"),
    "mood":        ("{name}无精打采地缩在角落... (´-ω-`)\n好无聊，陪我玩嘛~", "bored"),
}

# 碎碎念时段对应的图片素材
_SLOT_IMAGE = {
    "morning": "greeting_morning",
    "noon": "greeting_noon",
    "night": "greeting_night",
}


def create_scheduler(registry, send_fn, send_image_fn=None):
    scheduler = BackgroundScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        _tick_job,
        'interval',
        minutes=DECAY_INTERVAL_MIN,
        args=[registry, send_fn, send_image_fn],
        id='tick_job',
        misfire_grace_time=300,
    )
    scheduler.add_job(
        _chitchat_job,
        'interval',
        minutes=30,
        args=[registry, send_fn, send_image_fn],
        id='chitchat_job',
        misfire_grace_time=600,
    )
    scheduler.add_job(
        _auto_explore_job,
        'cron',
        hour=14, minute=0,
        args=[registry, send_fn, send_image_fn],
        id='auto_explore_job',
        misfire_grace_time=600,
    )
    scheduler.add_job(
        _diary_job,
        'cron',
        hour=22, minute=0,
        args=[registry, send_fn],
        id='diary_job',
        misfire_grace_time=600,
    )
    scheduler.add_job(
        _weekly_report_job,
        'cron',
        day_of_week='sun',
        hour=20, minute=0,
        args=[registry, send_fn],
        id='weekly_report_job',
        misfire_grace_time=600,
    )
    scheduler.add_job(
        _daily_personality_job,
        'cron',
        hour=0, minute=5,
        args=[registry, send_fn],
        id='daily_personality',
        timezone=TIMEZONE,
        misfire_grace_time=600,
    )
    return scheduler


def _tick_job(registry, send_fn, send_image_fn):
    """每 15 分钟执行：遍历所有用户，检查睡眠唤醒 + 属性衰减 + 告警"""
    for store in registry.all_active_stores():
        try:
            _tick_for_user(store, send_fn, send_image_fn)
        except Exception as e:
            print(f"  [scheduler] tick error for {store.user_id}: {e}")


def _tick_for_user(store, send_fn, send_image_fn):
    if store.pet is None or store.pet.get("stage") == "egg":
        return

    user_id = store.user_id
    name = store.get_pet_name()
    species_id = store.get_species_id() or "penguin"

    # === 睡眠检查 ===
    if store.pet.get("is_sleeping"):
        if not store.is_sleeping():
            send_fn(user_id, f"{name}睡醒了！精神满满！ヽ(>∀<☆)ノ")
            if send_image_fn:
                send_image_fn(user_id, "wakeup", species_id)
            print(f"  💤 {name} 睡醒了！")
        else:
            print(f"  💤 {name} 在睡觉，跳过衰减")
        return

    # === 探险检查 ===
    if store.pet.get("is_exploring"):
        if not store.is_exploring():
            result = store.finish_explore()
            if result:
                location, souvenir = result
                story = _generate_explore_story(name, location, species_id)
                souvenir_text = f"\n🎁 还带回了纪念品：{souvenir}！" if souvenir else ""
                send_fn(user_id, f"{name}从{location}回来了！✨\n\n{story}{souvenir_text}")
                if send_image_fn:
                    send_image_fn(user_id, "happy", species_id)
                print(f"  🌍 {name} 从{location}探险回来了")
        else:
            print(f"  🌍 {name} 在探险中...")

    # === 属性衰减 ===
    old_health = store.pet.get("health", 100)
    results = store.decay_all()
    if not results:
        return

    # === 告警 ===
    for stat, (old, new) in results.items():
        cfg = STAT_CONFIG.get(stat, {})
        threshold = cfg.get("alert_threshold", 20)
        if old >= threshold and new < threshold and stat in ALERT_INFO:
            msg, img_key = ALERT_INFO[stat]
            send_fn(user_id, msg.format(name=name))
            if send_image_fn:
                send_image_fn(user_id, img_key, species_id)

    new_health = store.pet.get("health", 100)
    if old_health >= 20 and new_health < 20 and new_health > 0:
        send_fn(user_id, f"🚨 {name}生病了，看起来很难受... (；´Д`)\n快带我去看医生！")
        if send_image_fn:
            send_image_fn(user_id, "sick", species_id)

    hunger = store.pet.get("hunger", 100)
    if hunger == 0:
        if results.get("hunger", (1, 1))[0] > 0:
            send_fn(user_id, f"{name}已经饿得不行了... (；´Д`)\n再不喂我就要饿晕啦！")

    print(f"  ⏰ [{store.user_id[:15]}] 衰减: " + ", ".join(f"{s}:{o}->{n}" for s, (o, n) in results.items()))

    # === 性格区间跨越通知 ===
    notifications = store.pet.pop("_pending_notifications", [])
    for msg in notifications:
        send_fn(user_id, msg)
    if notifications:
        store._save()


def _auto_explore_job(registry, send_fn, send_image_fn):
    """每日 14:00 自动出发探险（遍历所有用户）"""
    for store in registry.all_active_stores():
        try:
            _auto_explore_for_user(store, send_fn, send_image_fn)
        except Exception as e:
            print(f"  [scheduler] auto_explore error for {store.user_id}: {e}")


def _auto_explore_for_user(store, send_fn, send_image_fn):
    if store.pet is None or store.pet.get("stage") == "egg":
        return

    user_id = store.user_id
    name = store.get_pet_name()
    species_id = store.get_species_id() or "penguin"

    if store.pet.get("is_exploring") or store.pet.get("is_sleeping"):
        print(f"  🌍 自动探险跳过：{name}正忙")
        return
    if store.pet.get("stamina", 0) < 20:
        print(f"  🌍 自动探险跳过：{name}体力不足")
        return

    result = store.start_explore()
    if isinstance(result, tuple):
        location, until, duration = result
        if duration >= 60:
            time_desc = f"大约{duration // 60}小时{'多' if duration % 60 > 15 else ''}"
        else:
            time_desc = f"大约{duration}分钟"
        send_fn(user_id, f"{name}闲不住啦，自己背上小书包去{location}探险了！✨\n{time_desc}后回来~")
        if send_image_fn:
            send_image_fn(user_id, "exploring", species_id)
        print(f"  🌍 自动探险出发: {name} → {location}")


def _diary_job(registry, send_fn):
    """每日 22:00 生成宠物日记（遍历所有用户）"""
    for store in registry.all_active_stores():
        try:
            _diary_for_user(store, send_fn)
        except Exception as e:
            print(f"  [scheduler] diary error for {store.user_id}: {e}")


def _diary_for_user(store, send_fn):
    if store.pet is None or store.pet.get("stage") == "egg":
        return

    user_id = store.user_id
    name = store.get_pet_name()
    species_id = store.get_species_id() or "penguin"
    today = now().strftime("%Y-%m-%d")

    if store.diary and store.diary[-1].get("date") == today:
        return

    events = store.get_today_events()
    diary_content = _generate_diary(name, events, species_id)
    store.add_diary_entry(today, diary_content)

    send_fn(user_id, f"📖 {name}写了今天的日记~\n\n{diary_content}\n\n(发送「日记」可以翻看哦)")
    print(f"  📖 日记已生成: {today} ({store.user_id[:15]})")


def _weekly_report_job(registry, send_fn):
    """每周日 20:00 生成成长报告（遍历所有用户）"""
    for store in registry.all_active_stores():
        try:
            _weekly_report_for_user(store, send_fn)
        except Exception as e:
            print(f"  [scheduler] weekly_report error for {store.user_id}: {e}")


def _weekly_report_for_user(store, send_fn):
    if store.pet is None or store.pet.get("stage") == "egg":
        return

    user_id = store.user_id
    name = store.get_pet_name()
    species_id = store.get_species_id() or "penguin"
    pet = store.pet

    from datetime import timedelta
    today = now()
    week_ago = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    week_events = [h for h in store.history if h["time"][:10] >= week_ago]

    feeds = sum(1 for e in week_events if e["type"] == "feed")
    plays = sum(1 for e in week_events if e["type"] == "play")
    explores = [e["detail"].get("location", "") for e in week_events if e["type"] == "explore_end"]
    new_achs = [e for e in week_events if e["type"] == "achievement"]

    from species import get_species
    spec = get_species(species_id)
    species_emoji = spec["emoji"] if spec else "🐾"

    lines = [f"📊 {name}的每周成长报告\n"]
    lines.append(f"{species_emoji} 等级：Lv.{pet.get('level', 1)}  经验：{pet.get('xp', 0)}")
    lines.append(f"🍖 本周投喂：{feeds}次")
    lines.append(f"🎮 本周玩耍：{plays}次")
    if explores:
        lines.append(f"🌍 本周探险：{len(explores)}次（{'、'.join(set(explores))}）")
    lines.append(f"🎒 收藏品：{len(store.collection)}件")
    lines.append(f"🏆 成就：{len(pet.get('achievements', {}))}/18")

    stats = pet.get("stats", {})
    consecutive = stats.get("consecutive_days", 0)
    if consecutive >= 7:
        lines.append(f"🔥 连续活跃：{consecutive}天！")

    lines.append("")
    summary = _generate_weekly_summary(name, feeds, plays, explores, species_id)
    lines.append(summary)

    send_fn(user_id, "\n".join(lines))
    print(f"  📊 每周报告已发送 ({store.user_id[:15]})")


def _generate_weekly_summary(name, feeds, plays, explores, species_id="penguin"):
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
        result = parse_message(prompt, ctx, species_id=species_id)
        if result and result.get("reply"):
            return result["reply"]
    except Exception:
        pass
    return f"这周和主人在一起好开心！下周也要一起玩哦~ ❤️"


def _generate_diary(name, events, species_id="penguin"):
    """用 AI 生成日记，失败用模板"""
    feeds = events.get("feeds", 0)
    baths = events.get("baths", 0)
    plays = events.get("plays", 0)
    explores = events.get("explores", [])
    sleeps = events.get("sleeps", 0)

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
        result = parse_message(prompt, ctx, species_id=species_id)
        if result and result.get("reply"):
            return result["reply"]
    except Exception as e:
        print(f"  日记 AI 失败: {e}")

    return f"今天{event_desc}！过得好充实呀~ {name}最开心的就是有主人陪！明天也要一起玩哦！(≧▽≦)"


def _generate_explore_story(name, location, species_id="penguin"):
    """用 AI 生成探险小故事，失败则用预设"""
    try:
        from ai import parse_message
        prompt = f"用2-3句话描述{name}在{location}的探险经历，要有趣可爱，像童话故事一样。包含一个小发现或小收获。"
        ctx = {"name": name, "hunger": 80, "cleanliness": 80, "mood": 90, "stamina": 60, "health": 80, "level": 1}
        result = parse_message(prompt, ctx, species_id=species_id)
        if result and result.get("reply"):
            return result["reply"]
    except Exception as e:
        print(f"  探险故事生成失败: {e}")

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
# 碎碎念系统（主动情感触达，per-user 状态）
# ============================================================

_chitchat_lock = threading.Lock()
_chitchat_states = {}  # {user_id: {"sent_today": set(), "last_date": None, "last_interaction": None}}

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


def _get_chitchat_state(user_id):
    if user_id not in _chitchat_states:
        _chitchat_states[user_id] = {
            "sent_today": set(),
            "last_date": None,
            "last_interaction": None,
        }
    return _chitchat_states[user_id]


def mark_user_interaction(user_id):
    """外部调用：标记某用户刚互动过，触发冷却期"""
    with _chitchat_lock:
        state = _get_chitchat_state(user_id)
        state["last_interaction"] = now()


def _chitchat_job(registry, send_fn, send_image_fn):
    """每 30 分钟检查一次：是否该给用户发碎碎念（遍历所有用户）"""
    for store in registry.all_active_stores():
        try:
            _chitchat_for_user(store, send_fn, send_image_fn)
        except Exception as e:
            print(f"  [scheduler] chitchat error for {store.user_id}: {e}")


def _chitchat_for_user(store, send_fn, send_image_fn):
    if store.pet is None or store.pet.get("stage") == "egg":
        return

    user_id = store.user_id
    name = store.get_pet_name()
    species_id = store.get_species_id() or "penguin"
    current = now()
    today_str = current.strftime("%Y-%m-%d")

    with _chitchat_lock:
        cs = _get_chitchat_state(user_id)

        if cs["last_date"] != today_str:
            cs["sent_today"] = set()
            cs["last_date"] = today_str

        if store.pet.get("is_sleeping") or store.pet.get("is_exploring"):
            return

        last_interact = cs.get("last_interaction")
        if last_interact:
            minutes_since = (current - last_interact).total_seconds() / 60
            if minutes_since < CHITCHAT_COOLDOWN_MIN:
                return

        current_minutes = current.hour * 60 + current.minute
        eligible_slot = None
        for slot_key, (start_min, end_min, _) in CHITCHAT_SCHEDULE.items():
            if start_min <= current_minutes < end_min and slot_key not in cs["sent_today"]:
                eligible_slot = slot_key
                break

        if not eligible_slot:
            return

        if random.random() < 0.5:
            return

    msg = _generate_chitchat(name, store.pet, eligible_slot, species_id)
    if msg:
        send_fn(user_id, msg)
        if send_image_fn:
            img_key = _SLOT_IMAGE.get(eligible_slot, "idle")
            send_image_fn(user_id, img_key, species_id)
        with _chitchat_lock:
            cs = _get_chitchat_state(user_id)
            cs["sent_today"].add(eligible_slot)
        print(f"  💬 [{store.user_id[:15]}] 碎碎念 [{eligible_slot}]: {msg[:30]}...")


def _generate_chitchat(name, pet, slot_key, species_id="penguin"):
    """用 AI 生成碎碎念，失败用预设"""
    _, _, msg_type = CHITCHAT_SCHEDULE[slot_key]

    try:
        from ai import parse_message
        from species import get_species
        spec = get_species(species_id)
        species_name = spec["name"] if spec else "小宠物"
        prompt = (
            f"你是{name}，一只{species_name}宠物。现在是{msg_type}时间。"
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
        result = parse_message(prompt, ctx, species_id=species_id)
        if result and result.get("reply"):
            return result["reply"]
    except Exception as e:
        print(f"  碎碎念 AI 失败: {e}")

    templates = _CHITCHAT_FALLBACK.get(slot_key, ["{name}看着你~ (・ω・)"])
    return random.choice(templates).format(name=name)


def _daily_personality_job(registry, send_fn):
    """每日 0:05 执行：性格 offset 回归 baseline，重置日用量，亲密度忽视惩罚。"""
    for store in registry.all_active_stores():
        try:
            with store._lock:
                if store.pet is None or "trait_offsets" not in store.pet:
                    continue

                from personality import daily_decay_toward_baseline, compute_displayed_traits, update_intimacy, detect_band_crossings, get_crossing_message
                from species import get_species

                # 重置每日偏移用量
                store.pet["trait_daily_used"] = {k: 0.0 for k in store.pet.get("trait_offsets", {})}
                store.pet["intimacy_daily_gained"] = 0.0

                # Offset 回归 baseline
                offsets = store.pet.get("trait_offsets", {})
                new_offsets = daily_decay_toward_baseline(offsets)
                store.pet["trait_offsets"] = new_offsets

                # 重算展示值
                spec = get_species(store.get_species_id())
                if spec:
                    old_traits = dict(store.pet.get("traits", {}))
                    store.pet["traits"] = compute_displayed_traits(spec["baseline_traits"], new_offsets)

                    # 检测区间跨越 → 存入待发送通知
                    crossings = detect_band_crossings(old_traits, store.pet["traits"])
                    if crossings:
                        store.pet.setdefault("_pending_notifications", [])
                        for key, (old_band, new_band) in crossings.items():
                            msg = get_crossing_message(key, old_band, new_band, store.get_pet_name())
                            if msg:
                                store.pet["_pending_notifications"].append(msg)

                # 亲密度忽视惩罚
                last_at = store.pet.get("last_interaction_at")
                if last_at:
                    from datetime import datetime
                    try:
                        last_time = datetime.fromisoformat(last_at)
                        hours = (now() - last_time).total_seconds() / 3600
                        intimacy = store.pet.get("intimacy", 0.3)
                        new_int, _ = update_intimacy(intimacy, 0.0, interaction=False, hours_since_last=hours)
                        store.pet["intimacy"] = new_int
                    except (ValueError, TypeError):
                        pass

                store._save()
        except Exception as e:
            print(f"[scheduler] personality decay error for {store.user_id}: {e}")
