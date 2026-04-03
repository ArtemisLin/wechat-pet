# WeChat Pet (017Pet) - 交接文档

> 最后更新: 2026-03-28 16:30

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

**Phase 4 - 体验优化**
- E1 状态卡可视化：小Q风格，5属性进度条 + 经验进度 + 成就数 + 在一起天数 + 当前状态
- F1 碎碎念系统：每天4-6条主动消息，5个时段（早安/午饭/下午/晚间/晚安），AI生成+预设fallback，60分钟冷却期
- F2 图片变体系统：`_resolve_image_path()` 支持 `{key}_1.png` 变体随机选择，向后兼容单张
- B3 每日自动探险：14:00 cron 任务，自动出发探险，睡觉/探险中/体力不足时跳过
- F3 宠物日记：22:00 cron 自动生成，基于当天 history 事件，AI 写日记，用户"看日记"翻阅最近7天
- F4 收集系统：探险回来随机获得纪念品（10地点×4物品=40种），用户"背包"查看
- F5 昵称进化：用户说"我叫XXX"设置名字，AI prompt 按天数进化称呼（主人→名字→亲昵）
- F6 每周成长报告：周日 20:00 cron，统计本周活动+AI生成总结
- 属性恢复随机化：喂食(20-40)/洗澡(25-45)/玩耍(30-50)/治疗(30-50)，`_rand_restore()` 统一处理
- 探险中允许照顾操作：喂食/洗澡/治疗/状态/聊天放行，只拦截再探险+睡觉
- 玩耍活动池：12种本地随机活动（踢球/弹吉他/追蝴蝶/堆沙堡...），"出去玩"→本地玩耍，"探险"→远征
- 探险时长随机化：每个地点有不同时长范围（花园20-40min，雪山80-120min），不再固定30分钟
- 探险出发/看状态图片修复：`_with_achievements` 返回 `(text, img_key)` tuple，`format_status()` 返回 `(text, img)`

**图片资产（34张PNG）**
- 13张原始 + 21张占位（均为 idle.png 副本，待谷雨替换）
- 新增占位：wakeup.png, exploring.png, greeting_morning/noon/night.png, eating_1/2/3.png, idle_1/2/3.png, playing_1/2.png, happy_1/2.png, sleeping_1.png, bathing_1.png, hungry_1.png, exploring_1/2.png, wakeup_1.png

**动图研究（进行中）**
- GIF：已实测，微信 iLink image_item 只渲染第一帧，不可用
- APNG（Animated PNG）：**未实测**，方案B，下一步验证
- 验证方法：用 Pillow 生成2帧 APNG → `py ilink.py send-image test.apng` → 看微信端效果
- 其他备选：多帧连发（方案A）/ 视频消息（方案C，复杂度高）

**Bug修复**
- send_message 空响应判断、规则路由模糊匹配、改名档案一致性（替换历史中旧名字）
- B1: 问句误触发喂食修复（`_is_question()` 检测问句尾词，问句交 AI 处理）
- B2: 探险状态幻觉修复（空窗期自动结算 + AI prompt 注入探险位置）

### 已知问题 / 待优化

详见 `docs/优化计划.md`，剩余待处理项：

1. ~~"吃饭了吗"等问句误触发喂食~~ ✅ 已修复
2. 素材背景：透明PNG微信显示白底，当前#111111填充，后续自带场景背景（谷雨美术）
3. ~~每日自动探险（14:00）~~ ✅ 已实现
4. ~~探险状态幻觉~~ ✅ 已修复
5. AI生成像素画风格不完全统一（谷雨美术）
6. ~~成就/属性可视化（小Q状态卡）~~ ✅ 已实现
7. ~~主动碎碎念系统~~ ✅ 已实现
8. ~~图片变体系统~~ ✅ 代码已就绪，待谷雨出变体图
9. ~~宠物日记 / 收集系统 / 昵称进化 / 每周报告~~ ✅ 全部已实现

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
owner: {user_id, name, display_name} | history: 事件日志100条 | chat_history: 对话20轮
diary: 日记30天 | collection: 纪念品列表

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
9. 路由优先级：治疗>喂食；"出去玩/去玩"→play，"探险/去冒险"→explore
10. 问句检测 `_is_question()` 防止问句触发操作
21. 玩耍活动池：`PLAY_ACTIVITIES` 12种本地随机活动，`_play_reply()` 返回 `(text, img_key)` tuple
22. 探险时长随机化：`EXPLORE_LOCATIONS` dict 含 `(min, max)` 范围，`start_explore()` 返回 3-tuple `(location, until, duration)`
23. 图片修复：探险出发和状态卡均返回 `(text, img_key)` tuple，确保图片跟随文字发出
24. APNG 实验：Pillow 可生成 APNG，通过现有 `send_image_file()` 发送，等待微信端实测验证
11. 探险空窗期自动结算：`is_exploring` flag 为 True 但时间已过 → handle_message 中立即 finish_explore
12. 碎碎念调度：scheduler 30min 检查 + 50%随机跳过 + 60min 冷却 + `mark_user_interaction()` 标记互动
13. 图片变体：`_resolve_image_path()` glob `{key}_*.png` → 随机选，退回 `{key}.png` 单张
14. 自动探险：APScheduler cron 14:00，条件检查（睡觉/探险/体力）
15. 日记生成：22:00 cron，从 history 提取当天事件 → AI 生成 → diary 列表持久化
16. 收集系统：finish_explore 返回 (location, souvenir)，10地点×4纪念品池
17. 称呼进化：AI prompt 注入 `nickname_rule`，按 days_together 阈值（3/7/14天）升级
18. 周报：周日 20:00 cron，统计 history 最近7天事件
19. 属性恢复随机：`restore_amount` 支持 `(min, max)` tuple，`_rand_restore()` 统一处理
20. 探险中照顾放行：route action 不在 (explore, sleep) 则放行到 _handle_normal
