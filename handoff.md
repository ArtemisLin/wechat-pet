# WeChat Pet (017Pet) - 交接文档

> 最后更新: 2026-03-27 21:00

## 项目概述

基于微信 iLink (ClawBot) Bot API 的电子宠物 Agent，灵感来自 QQ 宠物。谷雨曾在腾讯做过 QQ 宠物项目。项目代号 wechat-pet。

## 当前状态

### 已完成

**Phase 1 - 基础喂养循环**
- 孵蛋→起名→喂食→饱腹衰减→主动喊饿

**Phase 2 - 5属性养成**
- 饱腹/清洁/心情/体力/健康 + XP/等级成长（baby→child→teen→adult）
- 15分钟 tick 调度，各属性不同衰减频率

**Phase 3 - 深度玩法**
- F1 睡眠状态机：睡觉30分钟，期间拦截消息，醒来主动通知+体力回满
- F2 时间感知：AI根据时段调整语气（早安/晚安/深夜关心）
- F3 对话记忆：最近20轮对话历史，持久化
- F4 探险系统：出发30分钟，回来带AI生成的故事，10个地点
- F5 成就系统：18个成就4大类，操作后自动检查解锁

**图片发送**
- iLink image_item 通道打通（静态PNG，AES-128-ECB + CDN）
- 13张像素素材集成，交互回复附带图片
- GIF动图不支持（微信只显示首帧）

**Bug修复**
- send_message 空响应判断、规则路由模糊匹配、改名档案一致性（替换历史中旧名字）

### 已知问题 / 待优化

1. "吃饭了吗"等问句误触发喂食（需区分问句和指令）
2. 素材背景：透明PNG微信显示白底，当前#111111填充，后续自带场景背景
3. 每日自动探险（14:00）尚未实现
4. 剩余5张素材待制作：healing/bored/hatching/happy/tired
5. AI生成像素画风格不完全统一

## 项目结构

```
017Pet/
├── CLAUDE.md, handoff.md, start.bat, .env.example
├── docs/ (设计文档 + 图片素材清单)
├── assets/penguin/ (13张PNG 256x256)
└── pet/ (config.py, ilink.py, core.py, ai.py, scheduler.py, image.py, .env)
```

## 数据模型 (pet_data.json, Schema v3)

pet: name, stage, 5属性, xp, level, is_sleeping/sleep_until, is_exploring/explore_until/explore_location, achievements, stats, _decay_tick
owner: {user_id, name} | history: 事件日志100条 | chat_history: 对话20轮

## 启动

```bash
cd pet && py ilink.py login   # 首次扫码
cd pet && py ilink.py start   # 启动bot
cd pet && py core.py           # 本地测试
```

## 关键技术决策

1. ProxyHandler({}) 绕过Clash | 2. 原子写入 tmp+os.replace | 3. threading.Lock
4. AES key Format B: base64(hex_string) | 5. CDN POST + x-encrypted-param
6. 15min tick + tick_mod | 7. 睡眠/探险暂停衰减 | 8. 改名替换历史中旧名字
9. 路由优先级：治疗>喂食，探险>玩耍
