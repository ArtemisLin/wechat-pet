# WeChat Pet

A virtual pet agent running on WeChat via the official iLink (ClawBot) Bot API. Inspired by QQ Pet (2005-2018).

基于微信 iLink (ClawBot) Bot API 的电子宠物 Agent，致敬 QQ 宠物。

## Features

- **Nurturing System** — 5 stats (hunger, cleanliness, mood, stamina, health) that decay over time
- **Pixel Art** — Pixel penguin images for actions and states (some assets are placeholders, replaceable)
- **Sleep Mode** — Pet sleeps for 30 min, wakes up automatically
- **Exploration** — Send your pet on adventures via command, it comes back with AI-generated stories
- **Achievement System** — 18 achievements across 4 categories
- **AI Personality** — Tested with DeepSeek, with time awareness and conversation memory
- **Growth System** — XP & levels (baby → child → teen → adult)

## Screenshots

```
🐧 小阿乌  Lv.1 宝宝
🍖 饱腹：😆 ████████░░ 80%
🛁 清洁：😊 ██████░░░░ 60%
❤️ 心情：😐 ████░░░░░░ 40%
⚡ 体力：😆 █████████░ 90%
💚 健康：😊 ████████░░ 80%
```

## Prerequisites

- **Python 3.13** (tested; other 3.10+ versions may work but not verified)
- **WeChat** with ClawBot plugin enabled
- **DeepSeek API Key** (get one at [platform.deepseek.com](https://platform.deepseek.com))

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/ArtemisLin/wechat-pet.git
cd wechat-pet
```

### 2. Install dependencies

```bash
pip install apscheduler cryptography Pillow
```

### 3. Configure

Copy the example config and fill in your API key:

```bash
cp .env.example pet/.env
```

Edit `pet/.env`:

```env
AI_API_KEY=your_deepseek_api_key_here
AI_BASE_URL=https://api.deepseek.com/chat/completions
AI_MODEL=deepseek-chat
BOT_NAME=my_pet
TIMEZONE=Asia/Shanghai
```

### 4. Login

Scan the QR code with WeChat to bind the bot:

```bash
cd pet
python ilink.py login
```

A URL will appear in the terminal. Open it in your browser, scan the QR code with WeChat, and confirm.

### 5. Start

```bash
python ilink.py start
```

Or on Windows, double-click `start.bat`.

### 6. Play!

Send messages to the ClawBot in WeChat:

| Command | Action |
|---------|--------|
| 孵蛋 | Hatch a new pet |
| 喂食 / 吃XX | Feed your pet |
| 洗澡 | Bathe your pet |
| 玩 / 陪我玩 | Play with your pet |
| 睡觉 | Pet sleeps for 30 min |
| 治疗 / 吃药 | Heal your pet |
| 出去玩吧 / 探险 | Send pet on a 30-min adventure |
| 看看 / 状态 | Check pet stats |
| 成就 | View achievements |
| 改名XX | Rename your pet |

Or just chat — the AI will respond in character!

## Project Structure

```
wechat-pet/
├── pet/
│   ├── config.py       # Configuration & constants
│   ├── ilink.py        # WeChat iLink communication layer
│   ├── core.py         # Pet engine, message routing, achievements
│   ├── ai.py           # AI personality (DeepSeek)
│   ├── scheduler.py    # Background jobs (stat decay, sleep/explore)
│   └── image.py        # Image encryption & CDN upload
├── assets/penguin/     # Pixel art assets (256x256 PNG)
├── docs/               # Design docs & asset guides
├── start.bat           # Windows one-click launcher
└── .env.example        # Config template
```

## Customization

### Custom Pixel Art

Replace images in `assets/penguin/` with your own 256x256 PNG files. Keep the same filenames:

`idle.png` `eating.png` `bathing.png` `playing.png` `sleeping.png` `healing.png` `hungry.png` `dirty.png` `bored.png` `sick.png` `hatching.png` `happy.png` `tired.png`

### Stat Tuning

Edit `pet/config.py` `STAT_CONFIG` to adjust decay rates, restore amounts, and alert thresholds.

### AI Model

Tested with DeepSeek. Other OpenAI-compatible APIs may work by changing `AI_BASE_URL` and `AI_MODEL` in `pet/.env`, but are not tested.

## Technical Notes

- **iLink Protocol**: HTTP/JSON, long-polling for messages, AES-128-ECB for media encryption
- **Image Upload**: `getuploadurl` → AES encrypt → POST to CDN → `sendmessage` with `image_item`
- **AES Key Format**: `base64(hex_string)` (Format B, not `base64(raw_bytes)`)
- **GIF**: Animated GIFs are sent successfully but WeChat client renders only the first frame (static)
- **Data**: Stored in `pet_data.json` with atomic writes (crash-safe)

## Acknowledgments

- Inspired by [QQ Pet](https://baike.baidu.com/item/QQ%E5%AE%A0%E7%89%A9/204567) (Tencent, 2005-2018)
- Built with [WeChat ClawBot iLink API](https://allclaw.org/blog/what-is-ilink-zh)
- AI powered by [DeepSeek](https://www.deepseek.com)
