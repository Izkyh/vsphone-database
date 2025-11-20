# 🚀 Quick Start Guide - VSPhone Monitor v5.0

## ⚡ 5 Menit Setup!

### 📦 Step 1: Download Files (1 menit)

Download 5 files ini:
```
✅ monitor_v5.py
✅ web_ui.py
✅ config.json
✅ requirements.txt
✅ README.md (optional)
```

---

### 🔧 Step 2: Install Dependencies (1 menit)

**Di Termux:**
```bash
pkg install python
pip install requests flask
```

**Di PC/Laptop:**
```bash
pip install -r requirements.txt
```

---

### ⚙️ Step 3: Edit config.json (2 menit)

Buka `config.json` dan edit bagian ini:

```json
{
  "accounts": [
    {
      "access_key_id": "GANTI_DENGAN_YOUR_ACCESS_KEY",
      "secret_access_key": "GANTI_DENGAN_YOUR_SECRET_KEY",
      
      "instances": [
        {
          "pad_code": "GANTI_PAD_CODE_ANDA",
          "name": "HP 1",
          
          "clones": [
            {
              "name": "Roblox Clone 1",
              "package": "com.delta.robloxgamedevice",
              "server_url": "https://www.roblox.com/share?code=YOUR_SERVER_CODE&type=Server"
            }
          ]
        }
      ]
    }
  ]
}
```

**Cara dapat data:**

1. **Access Key & Secret Key:**
   - Login ke VSPhone dashboard
   - Settings → API Keys
   - Copy kedua keys

2. **Pad Code:**
   - VSPhone dashboard
   - Pilih instance/HP
   - Copy pad code (contoh: APP2509077XXXXX)

3. **Package Name:**
   - Dari aplikasi yang sudah terinstall di VSPhone
   - Biasanya: `com.delta.robloxgamedevice`, `com.delta.robloxgamedevicea`, dll

4. **Server URL:**
   - Dari Roblox game yang ingin di-join
   - Format: `https://www.roblox.com/share?code=...&type=Server`

---

### 🚀 Step 4: Run! (1 menit)

**Simple Mode:**
```bash
python monitor_v5.py
```

**Full Features (Recommended):**
```bash
python monitor_v5.py --database --web-ui
```

**Output:**
```
╔══════════════════════════════════════════════════════════════╗
║      VSPhone Roblox Monitor v5.0                             ║
╚══════════════════════════════════════════════════════════════╝

🔍 Loading configuration...
✅ Configuration loaded successfully

📋 Configuration Summary:
   Accounts: 1
   Instances: 1
   Clones: 7
   Check Interval: 30s
   Database: ✅ Enabled
   Web UI: ✅ Enabled

🌐 Starting web dashboard on http://localhost:5000
🚀 Starting monitoring...

🔍 Starting check cycle for 7 clones...
✅ Cycle Complete (3.2s)
   Healthy: 7
```

---

### 🌐 Step 5: Open Dashboard (Optional)

Buka browser: **http://localhost:5000**

Dari HP lain? Gunakan IP:
```bash
# Cek IP dulu
ifconfig | grep inet

# Buka di browser
http://192.168.1.100:5000
```

---

## 🎯 Use Cases

### Case 1: Simple Setup (1 Account, 1 HP, 7 Clones)

**config.json:**
```json
{
  "global_settings": {
    "check_interval": 30
  },
  "accounts": [
    {
      "account_id": "main",
      "access_key_id": "YOUR_KEY",
      "secret_access_key": "YOUR_SECRET",
      "enabled": true,
      "instances": [
        {
          "pad_code": "APP2509077XXX",
          "name": "My Phone",
          "enabled": true,
          "clones": [
            {"name": "Clone 1", "package": "com.app1", "server_url": "...", "enabled": true},
            {"name": "Clone 2", "package": "com.app2", "server_url": "...", "enabled": true}
            // ... 5 more
          ]
        }
      ]
    }
  ]
}
```

**Run:**
```bash
python monitor_v5.py
```

---

### Case 2: Multi-Phone Setup (1 Account, 4 HP, 7 Clones Each = 28 Total)

**config.json:**
```json
{
  "accounts": [
    {
      "account_id": "main",
      "access_key_id": "YOUR_KEY",
      "secret_access_key": "YOUR_SECRET",
      "instances": [
        {
          "pad_code": "APP2509077HP1",
          "name": "HP 1",
          "clones": [
            {"name": "HP1 Clone 1", "package": "com.app1", "server_url": "..."},
            // ... 6 more
          ]
        },
        {
          "pad_code": "APP2509077HP2",
          "name": "HP 2",
          "clones": [
            {"name": "HP2 Clone 1", "package": "com.app1", "server_url": "..."},
            // ... 6 more
          ]
        },
        {
          "pad_code": "APP2509077HP3",
          "name": "HP 3",
          "clones": [ /* ... */ ]
        },
        {
          "pad_code": "APP2509077HP4",
          "name": "HP 4",
          "clones": [ /* ... */ ]
        }
      ]
    }
  ]
}
```

**Run:**
```bash
python monitor_v5.py --database --web-ui
```

---

### Case 3: Multi-Account Setup (2 Accounts, Each 2 HP, 10 Clones Each = 40 Total)

**config.json:**
```json
{
  "accounts": [
    {
      "account_id": "account_1",
      "account_name": "Main Account",
      "access_key_id": "KEY_1",
      "secret_access_key": "SECRET_1",
      "instances": [
        {"pad_code": "ACC1_HP1", "name": "Account1 HP1", "clones": [/* 10 clones */]},
        {"pad_code": "ACC1_HP2", "name": "Account1 HP2", "clones": [/* 10 clones */]}
      ]
    },
    {
      "account_id": "account_2",
      "account_name": "Backup Account",
      "access_key_id": "KEY_2",
      "secret_access_key": "SECRET_2",
      "instances": [
        {"pad_code": "ACC2_HP1", "name": "Account2 HP1", "clones": [/* 10 clones */]},
        {"pad_code": "ACC2_HP2", "name": "Account2 HP2", "clones": [/* 10 clones */]}
      ]
    }
  ]
}
```

**Run:**
```bash
python monitor_v5.py --database --web-ui
```

---

### Case 4: Mega Setup (10 Accounts, 100 Clones Total)

Sama seperti Case 3, tapi multiply!

**Tips:**
- Enable database: `--database`
- Enable web UI: `--web-ui`
- Use screen/tmux untuk 24/7:
  ```bash
  screen -S monitor
  python monitor_v5.py --database --web-ui
  # Ctrl+A lalu D untuk detach
  ```

---

## 🔥 Pro Tips

### Tip 1: Running 24/7 di Termux

```bash
# Install termux-wake-lock
pkg install termux-api
termux-wake-lock

# Use screen
screen -S vsphone
python monitor_v5.py --database --web-ui

# Detach: Ctrl+A lalu D
# Reattach: screen -r vsphone
```

---

### Tip 2: Remote Access Dashboard

```bash
# Find your IP
ifconfig | grep inet

# Share dashboard ke network
# Edit web_ui.py atau just use default (sudah 0.0.0.0)

# Access dari device lain
http://YOUR_IP:5000
```

---

### Tip 3: Telegram Notifications

Edit `config.json`:
```json
{
  "global_settings": {
    "telegram_bot_token": "YOUR_BOT_TOKEN",
    "telegram_chat_id": "YOUR_CHAT_ID"
  }
}
```

Get bot token: @BotFather
Get chat ID: @userinfobot

---

### Tip 4: Disable Clone Sementara

Tidak perlu delete, cukup set `enabled: false`:

```json
{
  "clones": [
    {
      "name": "Clone 1",
      "package": "com.app1",
      "enabled": false  // ← Disabled
    }
  ]
}
```

---

### Tip 5: Multiple Server URLs

Kalau clone-clone Anda join server berbeda:

```json
{
  "clones": [
    {
      "name": "Clone 1 - Server A",
      "package": "com.app1",
      "server_url": "https://roblox.com/share?code=SERVER_A&type=Server"
    },
    {
      "name": "Clone 2 - Server B",
      "package": "com.app2",
      "server_url": "https://roblox.com/share?code=SERVER_B&type=Server"
    }
  ]
}
```

---

## ❓ Common Questions

### Q: Apakah harus restart script kalau edit config?

**A:** YA. Setelah edit `config.json`:
1. Stop script: `Ctrl+C`
2. Start lagi: `python monitor_v5.py`

---

### Q: Bisa monitoring sambil main game?

**A:** YA! Script ini tidak interfere dengan device.

---

### Q: Butuh install di tiap VSPhone instance?

**A:** TIDAK! Install sekali di 1 device (PC/HP/Termux), bisa monitor semua VSPhone instances via API.

---

### Q: Apakah script ini aman?

**A:** YA! 
- ✅ Open source (bisa di-review)
- ✅ No data keluar selain ke VSPhone API
- ✅ Credentials hanya di config.json lokal

---

## 🆘 Troubleshooting

### Error: "Config file not found"

```bash
# Pastikan config.json ada di folder yang sama
ls -la
# Harus ada: monitor_v5.py, web_ui.py, config.json
```

---

### Error: "requests library not found"

```bash
pip install requests flask
```

---

### Error: "API timeout"

- Check internet connection
- Verify VSPhone API credentials
- Try increase retry di config:
  ```json
  {"global_settings": {"max_retry_attempts": 5}}
  ```

---

## 📞 Need Help?

1. Read **README.md** for detailed docs
2. Check **vsphone_multi.log** for errors
3. Enable debug: `python monitor_v5.py --debug`

---

## 🎉 Done!

Selamat! Anda sudah setup VSPhone Monitor v5.0!

**Next:**
- [ ] Add more clones ke config
- [ ] Enable Telegram notifications
- [ ] Setup 24/7 dengan screen/tmux
- [ ] Explore web dashboard
- [ ] Check database analytics

**Happy monitoring! 🚀**