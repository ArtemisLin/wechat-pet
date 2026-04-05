# WeChat Pet (017Pet) V2 — 交接文档

> 最后更新: 2026-04-05 (Phase 1-5 全部完成)

## 项目概述

基于微信 iLink (ClawBot) Bot API 的电子宠物 Agent。谷雨曾在腾讯做过 QQ 宠物项目。
V2 目标：从技术 demo 升级为有社交货币价值的产品。

## 分支策略

- 工作分支: `phase1-multiuser`（所有 Phase 1-5 的提交都在此分支）
- 全部 5 个 Phase 完成后才合并回 `main`

## 施工进度

### Phase 1 ✅ 多用户 + 品种系统

- 存储: 单文件 → `data/{user_id}/pet.json` 目录制
- 6 品种: penguin/dinosaur/fox/rabbit/owl/dragon
- MessageHandler: 单例 → `registry.get_or_create(user_id)` per-user
- AI prompt: 按品种动态生成
- Scheduler: 遍历 `registry.all_active_stores()`
- Schema v4 → v5（含性格字段）

### Phase 2 ✅ 性格 + 亲密度系统

- 5维性格: extrovert/brave/greedy/curious/blunt，范围 [0.1, 0.9]
- 双层架构: displayed_trait = species_baseline + learned_offset
- 互动漂移: feed→greedy, play→extrovert, explore→brave+curious
- 3步孵化塑形流程（hatching_1/2/3 → ask_name_v2 → ask_owner_name）
- 亲密度: 互动+0.01（日上限+0.05），24h无互动-0.03
- 每日0:05 衰减回归 + 亲密度忽视惩罚
- AI prompt 注入性格描述 + 亲密度行为指引

### Phase 3 ✅ AI 生图 + 视觉合成（commit 06bb4ef）

**新增文件:**
- `pet/image_gen.py` — 即梦 API 生图引擎（volcengine SDK，req_key: jimeng_seedream46_cvtob）
- `pet/compositor.py` — Pillow 三层视觉合成器（场景+角色+配饰）
- `pet/assets_manager.py` — 素材管理器（三级 fallback + 成长阶段解锁）

**修改文件:**
- `pet/config.py` — IMAGE_GEN_AK/SK 配置
- `pet/core.py` — 孵化完成后 `_async_gen_hatch_images()` 异步生成 4 张图
- `pet/store.py` — 升级时 `_async_gen_stage_images()` 异步补图
- `pet/ilink.py` — `_send_image_by_key()` 优先用 AI 缓存图；typing 节奏系统

**即梦 API 配置（已在 .env 中配好）:**
- 火山引擎 AK/SK 认证，通过 volcengine SDK
- req_key: `jimeng_seedream46_cvtob`（Seedream 4.6）
- 异步模式: submit → poll（约 6-9 秒出图）
- 1024x1024 输出，force_single=True
- ⚠️ SDK 的 `cv_sync2async_submit_task()` 必须传 dict，不能传 json string

**关键设计:**
- 异步生图不阻塞用户（daemon thread）
- 图片缓存: `data/{user_id}/images/{key}.png`
- 三级素材 fallback: AI 缓存 → 品种预制 → penguin 默认
- 成长阶段解锁: baby(base/idle/happy/sleeping) → child(eating/bathing) → teen(playing/exploring) → adult(sick)

**当前状态:**
- API 调通，生图效果已验证（Q版像素企鹅）
- 39 个测试全部通过
- 已 commit (06bb4ef)

### Phase 4 ✅ 额度系统（commit 62fc6f3）

**新增文件:**
- `pet/quota.py` — 额度管理器（QuotaManager + DegradationLevel + 消耗常量）

**修改文件:**
- `pet/store.py` — schema v5→v6，`_default_pet` 加 quota 字段，迁移逻辑，成长生图加额度检查
- `pet/core.py` — AI 对话前检查陪伴能量+降级，孵化生图检查星星，状态卡显示额度，"充值"命令
- `pet/ai.py` — `parse_message` 新增 `degradation` 参数，轻度降级时 max_tokens 减半
- `pet/scheduler.py` — 每日重置陪伴能量，闲聊降级控制，日记/周报消耗星星

**关键设计:**
- 双能量：陪伴能量（每日恢复100，聊天消耗）+ 创作星星（初始100，生图/日记/周报消耗）
- 四级渐进降级：NORMAL → LIGHT（AI回复变短）→ MEDIUM（不生新图）→ DEEP（预制模板）
- 消耗表：AI聊天1陪伴能量，生图10星星，日记1星星，周报2星星
- 充值命令（V1手动转账）

**当前状态:**
- 50 个测试全部通过
- 已 commit (62fc6f3)

### Phase 5 ✅ 传播系统（commit dcb3492）

**新增文件:**
- `pet/highlights.py` — 高光时刻引擎（S/A/B 三级检测）
- `pet/cards.py` — Pillow 卡片生成器（性格签卡/名片/成就卡/周报卡）
- `pet/invite.py` — 邀请码系统（4位码，持久化到 invites.json）
- `pet/h5.py` — 轻量成长册 H5 静态页生成器

**修改文件:**
- `pet/core.py` — 邀请码验证+领养流程、"名片"/"邀请码"命令、孵化时生成签卡和邀请码、邀请者奖励星星

**关键设计:**
- 高光分级：S 级（满月/成年礼/SSR）→ 卡片+分享提示，A 级 → 轻提醒，B 级 → 只记录
- 邀请码：孵化完成赠送 1 个码，使用后邀请者得 10 星星
- 名片卡：Pillow 生成 1024x600 横版名片，缓存到 images/
- H5 成长册：base64 内嵌角色图的纯静态 HTML

**当前状态:**
- 58 个测试全部通过
- 已 commit (dcb3492)

## 项目结构

```
017Pet/
├── CLAUDE.md, handoff.md, start.bat, .env.example
├── docs/                     设计文档 + 施工计划
│   └── plans/                Phase 1-5 施工计划
├── assets/
│   ├── penguin/              企鹅预制素材 (34张 PNG)
│   ├── scenes/               场景背景（暂空）
│   └── templates/            模板（暂空）
├── tests/                    58 个测试
│   ├── test_store.py         存储层 (11)
│   ├── test_integration.py   集成 (9)
│   ├── test_personality.py   性格引擎 (10)
│   ├── test_species.py       品种 (5)
│   ├── test_image_gen.py     生图引擎 (4)
│   ├── test_quota.py         额度系统 (11)
│   └── test_invite.py        邀请码系统 (8)
└── pet/
    ├── config.py             配置（AI/生图API/宠物参数）
    ├── ilink.py              通信层（登录/轮询/发送/typing）
    ├── core.py               宠物引擎 + 消息路由
    ├── ai.py                 AI 对话层（性格/时间感知/对话记忆）
    ├── scheduler.py          调度器（衰减/碎碎念/日记/周报/性格衰减）
    ├── store.py              多用户存储层（UserPetStore + PetRegistry）
    ├── species.py            6 品种定义
    ├── personality.py        性格引擎（5维/漂移/衰减/亲密度）
    ├── image_gen.py          即梦 AI 生图引擎
    ├── compositor.py         Pillow 三层合成器
    ├── assets_manager.py     素材管理器
    ├── quota.py              额度系统（双能量+渐进降级）
    ├── highlights.py         高光时刻引擎（S/A/B 分级）
    ├── cards.py              Pillow 卡片生成器（4种模板）
    ├── invite.py             邀请码系统（4位码）
    ├── h5.py                 轻量成长册 H5 生成器
    ├── image.py              AES 加密 + CDN 上传
    └── .env                  密钥（不提交）
```

## 数据模型 (Schema v5)

```
data/{user_id}/
  pet.json                    宠物数据
  images/                     AI 生成的图片缓存
    {key}.png                 生成的图片
    {key}.meta.json           生成参数（prompt/model/seed）
```

pet.json 字段: name, species, stage, 5属性, xp, level,
sleeping/exploring 状态, achievements, stats,
traits, trait_offsets, trait_daily_used, intimacy, intimacy_daily_gained, last_interaction_at,
quota (stars, companion_energy, initial_stars, total_recharged)

## 启动

```bash
cd pet && py ilink.py start   # 启动 bot（含 APScheduler）
py -m pytest tests/ -v        # 跑测试
```

## 下一步

Phase 1-5 全部完成。下一步：
1. 合并 `phase1-multiuser` → `main`
2. 端到端真机测试（微信 iLink 环境）
3. 根据使用反馈迭代优化
