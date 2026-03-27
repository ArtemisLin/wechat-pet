# 017Pet - 微信电子宠物 Agent

## 项目概述

基于微信 iLink (ClawBot) Bot API 的电子宠物 Agent，通过微信聊天窗口与用户互动，文字版起步。灵感来自 QQ 宠物（2005-2018），谷雨曾在腾讯参与该项目。

## 技术栈

- Python（与 015fridge 一致的技术选型）
- 微信 iLink Bot API（官方 ClawBot 协议）
- AI 大模型（性格/对话生成）

## iLink 协议关键要素

### 接入域名
- 业务 API: `https://ilinkai.weixin.qq.com`
- CDN: `https://novac2c.cdn.weixin.qq.com/c2c`

### 认证流程
1. `GET /ilink/bot/get_bot_qrcode?bot_type=3` → 获取二维码
2. `GET /ilink/bot/get_qrcode_status?qrcode=xxx` → 轮询状态（wait/scaned/confirmed/expired）
3. confirmed 返回 `bot_token` + `ilink_bot_id` + `ilink_user_id`
4. **无 token 刷新机制**，过期只能重新扫码

### 通用请求头（所有业务 POST）
```
Content-Type: application/json
AuthorizationType: ilink_bot_token
Authorization: Bearer ${bot_token}
X-WECHAT-UIN: base64(String(randomUint32()))  # 每次随机，防重放
```

### 消息接收（长轮询）
- `POST /ilink/bot/getupdates`
- 服务端 hold 最多 35 秒
- `get_updates_buf` 是 opaque cursor，必须原样缓存和回传
- 首次传空字符串

### 消息发送
- `POST /ilink/bot/sendmessage`
- **context_token 是核心**：每条收到的消息都带，回复时必须原样带上
- 以 (botId, userId) 为 key 缓存最近一次 token
- `message_type=2`（BOT），`message_state=2`（FINISH）
- `client_id` 必须全局唯一（UUID 或 前缀+时间戳+随机）
- 文本保守上限 2000 字符，长消息在 `\n\n` / `\n` / 空格处分片
- 一条请求只发一个 MessageItem

### Typing 状态（"正在输入"）
1. `POST /ilink/bot/getconfig` → 获取 `typing_ticket`
2. `POST /ilink/bot/sendtyping` → `status=1` 开始 / `status=2` 取消
3. 长时间处理每 5 秒发一次 keepalive

### 消息类型
| type | 类型 | 子结构 |
|------|------|--------|
| 1 | 文本 | `text_item.text` |
| 2 | 图片 | `image_item` (CDN + AES加密) |
| 3 | 语音 | `voice_item` (含 `text` 语音转文字) |
| 4 | 文件 | `file_item` |
| 5 | 视频 | `video_item` |

### 错误处理
| ret | 含义 | 处理 |
|-----|------|------|
| 0 | 成功 | 正常 |
| -14 | session expired | 立即停止，清凭证，重新扫码 |
| -2 | 参数错误 | 检查请求 |
| 普通失败 | — | 等 2s 重试，连续 3 次退避 30s |

## 015FRIDGE 踩坑经验（必读）

### P0 级
1. **context_token 24h 限制**：Bot 只能在有有效 context_token 时发消息，缓存所有收到的 token，提醒发送失败时攒到用户下次发消息再投递
2. **日期比较 bug**：`datetime.now()` vs `date()` 导致 off-by-one，所有日期比较用 `.date()` 对象
3. **提醒架构**：不能在 polling loop 里检查提醒（会被长轮询阻塞），用 APScheduler 独立后台线程
4. **原子写入**：持久化数据先写 tmp 再 `os.replace()`，防崩溃丢数据
5. **时区**：用 `zoneinfo.ZoneInfo(TIMEZONE)` 而非系统时间，bot 和用户可能不在同一时区

### 高优先级
6. **复合句处理**：含"和"/"、"或 >15 字符的文本不要用规则匹配，交给 AI 解析
7. **代理绕过**：iLink API 和 AI API 都用 `ProxyHandler({})` 绕过 Clash
8. **撤销栈按用户隔离**：多用户场景 undo 不能串
9. **危险操作二次确认**：清空等不可逆操作需要确认窗口

### 架构参考（015FRIDGE 3 层设计）
```
ilink.py — 通信层（薄）：收发消息、维护 cursor、缓存 context_token
core.py  — 核心层：规则路由（<1ms）+ 领域操作 + 持久化 + 记忆
ai.py    — AI 层（3-10s）：复杂语义解析、分类、名字提取
```
规则优先（零延迟），AI 兜底（允许 3-10s 延迟）。

## NEVER
- 硬编码 API Key（用 .env）
- iLink API 走 Clash 代理（用 ProxyHandler({})）
- 在 Bash heredoc 中用 `\n` 写 .py 文件（用 chr(10)）
- 跳过验证就说完成

## ALWAYS
- 改完代码跑一遍验证
- 复杂任务先 Plan Mode
- 出错立即停止重新规划
