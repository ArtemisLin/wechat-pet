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
