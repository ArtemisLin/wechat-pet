"""
017Pet — 后台调度（Phase 3: 睡眠状态机 + 多属性衰减 + 图片）
"""

from apscheduler.schedulers.background import BackgroundScheduler
from config import TIMEZONE, STAT_CONFIG, DECAY_INTERVAL_MIN

ALERT_INFO = {
    "hunger":      ("{name}趴在地上，肚子咕咕叫... (\u00b4;\u03c9;`)\n快来喂我吃东西嘛~", "hungry"),
    "cleanliness": ("{name}脏兮兮的，浑身不舒服... (>_<)\n给我洗个澡嘛~", "dirty"),
    "mood":        ("{name}无精打采地缩在角落... (\u00b4-\u03c9-`)\n好无聊，陪我玩嘛~", "bored"),
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
                    send_image_fn(owner_id, "idle")
            print(f"  \U0001f4a4 {name} 睡醒了！")
        else:
            # 还在睡，跳过衰减
            print(f"  \U0001f4a4 {name} 在睡觉，跳过衰减")
        return

    # === 探险检查：到时间了就返回 ===
    if pet_store.pet.get("is_exploring"):
        if not pet_store.is_exploring():  # 到时间了
            location = pet_store.finish_explore()
            if owner_id and location:
                # 生成探险故事
                story = _generate_explore_story(name, location)
                send_fn(owner_id, f"{name}从{location}回来了！\u2728\n\n{story}")
                if send_image_fn:
                    send_image_fn(owner_id, "happy")
                print(f"  \U0001f30d {name} 从{location}探险回来了")
        else:
            print(f"  \U0001f30d {name} 在探险中...")

    # === 属性衰减 ===
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

    health = pet_store.pet.get("health", 100)
    if health < 20 and health > 0:
        send_fn(owner_id, f"\U0001f6a8 {name}生病了，看起来很难受... (\uff1b\u00b4\u0414`)\n快带我去看医生！")
        if send_image_fn:
            send_image_fn(owner_id, "sick")

    hunger = pet_store.pet.get("hunger", 100)
    if hunger == 0:
        if results.get("hunger", (1, 1))[0] > 0:
            send_fn(owner_id, f"{name}已经饿得不行了... (\uff1b\u00b4\u0414`)\n再不喂我就要饿晕啦！")

    print(f"  \u23f0 衰减: " + ", ".join(f"{s}:{o}->{n}" for s, (o, n) in results.items()))


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
