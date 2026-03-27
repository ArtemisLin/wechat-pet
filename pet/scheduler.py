"""
017Pet — 后台调度（Phase 2: 多属性衰减 + 主动提醒）
"""

from apscheduler.schedulers.background import BackgroundScheduler
from config import TIMEZONE, STAT_CONFIG, DECAY_INTERVAL_MIN

ALERT_MESSAGES = {
    "hunger":      "{name}趴在地上，肚子咕咕叫... (\u00b4;\u03c9;`)\n快来喂我吃东西嘛~",
    "cleanliness": "{name}脏兮兮的，浑身不舒服... (>_<)\n给我洗个澡嘛~",
    "mood":        "{name}无精打采地缩在角落... (\u00b4-\u03c9-`)\n好无聊，陪我玩嘛~",
}


def create_scheduler(pet_store, send_fn):
    scheduler = BackgroundScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        _decay_job,
        'interval',
        minutes=DECAY_INTERVAL_MIN,
        args=[pet_store, send_fn],
        id='stat_decay',
        misfire_grace_time=300,
    )
    return scheduler


def _decay_job(pet_store, send_fn):
    """统一衰减 + 阈值告警"""
    if pet_store.pet is None or pet_store.pet.get("stage") == "egg":
        return

    results = pet_store.decay_all()
    if not results:
        return

    owner_id = pet_store.owner.get("user_id")
    if not owner_id:
        return

    name = pet_store.pet.get("name", "小企鹅")

    for stat, (old, new) in results.items():
        cfg = STAT_CONFIG.get(stat, {})
        threshold = cfg.get("alert_threshold", 20)
        if old >= threshold and new < threshold and stat in ALERT_MESSAGES:
            send_fn(owner_id, ALERT_MESSAGES[stat].format(name=name))

    # 健康告警
    health = pet_store.pet.get("health", 100)
    if health < 20 and health > 0:
        send_fn(owner_id, f"\U0001f6a8 {name}生病了，看起来很难受... (\uff1b\u00b4\u0414`)\n快带我去看医生！")

    # 饿到 0
    hunger = pet_store.pet.get("hunger", 100)
    if hunger == 0:
        if results.get("hunger", (1, 1))[0] > 0:
            send_fn(owner_id, f"{name}已经饿得不行了... (\uff1b\u00b4\u0414`)\n再不喂我就要饿晕啦！")

    print(f"  \u23f0 衰减: " + ", ".join(f"{s}:{o}->{n}" for s, (o, n) in results.items()))
