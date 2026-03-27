# WeChat Pet (017Pet) - 交接文档

> 最后更新: 2026-03-27

## 项目概述

基于微信 iLink (ClawBot) Bot API 的电子宠物 Agent，灵感来自 QQ 宠物。谷雨曾在腾讯做过 QQ 宠物项目。

## 当前状态

### 已完成
- **Phase 1**: 基础喂养循环（孵蛋→喂食→饱腹衰减→主动喊饿）
- **Phase 2**: 5属性养成（饱腹/清洁/心情/体力/健康）+ XP/等级成长
- **图片发送**: iLink image_item 通道打通（静态PNG，AES-128-ECB加密上传CDN）
- **像素素材**: 13张占位图已集成，谷雨提供了8张真实像素画（idle/eating/bathing/playing/sleeping/sick/dirty/hungry）
- **Bug修复**: send_message 空响应误判、规则路由模糊匹配
- **F1 睡眠状态机**: 睡觉30分钟，期间回复"在睡觉"，醒来主动通知，体力回满
- **F2 时间感知**: AI prompt 根据时段调整语气（早安/晚安/深夜关心）
- **F3 对话记忆**: 保留最近20轮对话历史，AI能记住上下文
- **F4 探险系统**: 出发探险30分钟，回来带AI生成的故事，10个地点

### 进行中
- **F5 成就系统**: 18个成就，分类（养成/成长/探险/特殊），还未开始写代码

### 待做
- GIF动图不支持（微信只显示首帧），已确认是iLink限制
- 素材背景问题：透明PNG在微信显示白底，当前用#111111填充，后续谷雨提供自带场景背景的素材
- 改名功能：代码已修复但需谷雨重启bot确认
- "问你要不要吃饭就直接吃了"问题：AI对话中提到食物触发了喂食规则路由，需优化匹配逻辑
- 每日自动探险（下午14:00）
- 剩余5张素材待制作：healing/bored/hatching/happy/tired

## 项目结构

```
017Pet/
├── CLAUDE.md              # 项目规则 + iLink协议速查
├── handoff.md             # 本文件
├── start.bat              # 一键启动
├── .env.example           # 配置模板
├── docs/
│   ├── 2026-03-26-pet-agent-design.md  # 设计文档
│   └── 图片素材.md                      # 素材清单和生成指南
├── assets/penguin/        # 像素素材（13张PNG）
└── pet/                   # 主代码
    ├── config.py          # 环境变量、时区、属性参数、成长常量
    ├── ilink.py           # iLink通信层 + CLI + 主入口
    ├── core.py            # PetStore + MessageHandler + 状态显示
    ├── ai.py              # AI性格对话（DeepSeek，时间感知）
    ├── scheduler.py       # 后台调度（属性衰减+睡眠唤醒+探险返回）
    ├── image.py           # 图片加密上传模块（AES-128-ECB + CDN）
    └── .env               # 用户配置（不入库）
```

## 启动/测试

```bash
# 启动bot
cd pet && py ilink.py start
# 或双击 start.bat

# 登录（首次）
cd pet && py ilink.py login

# 发送测试图片
cd pet && py ilink.py send-image

# 本地测试
cd pet && py core.py
```

## 关键技术决策

1. iLink API 代理绕过：`ProxyHandler({})` + 清除环境变量
2. 数据持久化：`pet_data.json` 原子写入（tmp + os.replace）
3. 线程安全：PetStore._save() 用 threading.Lock
4. AES key 格式：Format B `base64(hex_string)`（不是 base64(raw_bytes)）
5. CDN上传：POST（不是PUT），x-encrypted-param 响应头用于 sendmessage
6. 衰减调度：15分钟tick，各属性用 tick_mod 控制不同频率
7. 睡眠/探险期间：属性衰减暂停，消息回复提示状态

## 数据模型 (pet_data.json)

Schema v2，主要字段：
- pet: name, stage, hunger/cleanliness/mood/stamina/health, xp, level, is_sleeping, sleep_until, is_exploring, explore_until, explore_location, _decay_tick
- owner: user_id, name
- history: 事件日志（最近100条）
- chat_history: 对话记忆（最近20轮/40条）

## 015FRIDGE 踩坑经验（仍然适用）

- context_token 24h限制，缓存所有token
- session过期 ret=-14 需重新扫码
- APScheduler独立线程不阻塞polling
- 时区用 zoneinfo.ZoneInfo 不用系统时间
