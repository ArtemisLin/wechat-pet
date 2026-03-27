"""
017Pet — 后台调度（饥饿衰减 + 主动提醒）
"""

from apscheduler.schedulers.background import BackgroundScheduler
from config import TIMEZONE, HUNGER_DECAY_INTERVAL_MIN, HUNGER_ALERT_THRESHOLD


def create_scheduler(pet_store, send_fn):
    """
    创建后台调度器。
    send_fn(user_id, text) - 主动发送消息的函数
    """
    scheduler = BackgroundScheduler(timezone=TIMEZONE)

    scheduler.add_job(
        _hunger_decay_job,
        'interval',
        minutes=HUNGER_DECAY_INTERVAL_MIN,
        args=[pet_store, send_fn],
        id='hunger_decay',
        misfire_grace_time=300,
    )

    return scheduler


def _hunger_decay_job(pet_store, send_fn):
    """饥饿衰减 + 主动喊饿"""
    if pet_store.pet is None or pet_store.pet.get("stage") == "egg":
        return

    old_hunger = pet_store.pet["hunger"]
    new_hunger = pet_store.decay_hunger()

    if new_hunger is None:
        return

    print(f"  ⏰ 饥饿衰减: {old_hunger} -> {new_hunger}")

    # 跨过阈值时主动发消息
    if old_hunger >= HUNGER_ALERT_THRESHOLD and new_hunger < HUNGER_ALERT_THRESHOLD:
        owner_id = pet_store.owner.get("user_id")
        if owner_id:
            name = pet_store.pet.get("name", "小企鹅")
            send_fn(owner_id, f"{name}趴在地上，肚子咕咕叫... (´;ω;`)\n快来喂我吃东西嘛~")

    # 饿到 0 时再喊一次
    if old_hunger > 0 and new_hunger == 0:
        owner_id = pet_store.owner.get("user_id")
        if owner_id:
            name = pet_store.pet.get("name", "小企鹅")
            send_fn(owner_id, f"{name}已经饿得不行了... (；´Д`)\n再不喂我就要饿晕啦！")
