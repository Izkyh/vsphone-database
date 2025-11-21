#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║    VSPhone Monitor v5.3.1 - RESTART LOOP FIXED              ║
║                                                              ║
║  ✅ State tracking untuk prevent restart loop                ║
║  ✅ Grace period setelah restart                             ║
║  ✅ Persistent state across script restarts                  ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""

import requests
import hashlib
import hmac
import json
import time
import sys
import os
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import threading
import pickle

VERSION = "5.3.1 FIXED"
BASE_URL = "https://api.vsphone.com"

# ═══════════════════════════════════════════════════════════════
#                    State Manager (NEW!)
# ═══════════════════════════════════════════════════════════════

class StateManager:
    """
    Track restart state untuk prevent restart loops
    State disimpan di file agar persist across script restarts
    """
    
    def __init__(self, state_file='vsphone_state.pkl'):
        self.state_file = Path(state_file)
        self.lock = threading.Lock()
        self.states = {}  # {clone_key: {'last_restart': datetime, 'grace_until': datetime}}
        self.load_state()
    
    def get_clone_key(self, clone_data):
        """Generate unique key untuk clone"""
        return f"{clone_data['account_id']}:{clone_data['instance_pad_code']}:{clone_data['clone_package']}"
    
    def load_state(self):
        """Load state dari file"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'rb') as f:
                    self.states = pickle.load(f)
                
                # Clean up old states (lebih dari 1 jam)
                now = datetime.now()
                expired = [k for k, v in self.states.items() 
                          if (now - v.get('last_restart', now)).total_seconds() > 3600]
                
                for key in expired:
                    del self.states[key]
                
                print(f"[INFO] 📂 Loaded state: {len(self.states)} clones tracked")
            except Exception as e:
                print(f"[WARNING] ⚠️  Failed to load state: {e}")
                self.states = {}
    
    def save_state(self):
        """Save state ke file"""
        try:
            with open(self.state_file, 'wb') as f:
                pickle.dump(self.states, f)
        except Exception as e:
            # Silent fail - tidak perlu log di sini
            pass
    
    def mark_restart(self, clone_data, grace_seconds=120):
        """
        Mark bahwa clone baru saja di-restart
        Grace period default: 120 detik (2 menit)
        """
        with self.lock:
            key = self.get_clone_key(clone_data)
            now = datetime.now()
            
            self.states[key] = {
                'last_restart': now,
                'grace_until': now + timedelta(seconds=grace_seconds),
                'restart_count': self.states.get(key, {}).get('restart_count', 0) + 1
            }
            
            self.save_state()
            
            log_message(f"      🕐 Grace period: {grace_seconds}s until {self.states[key]['grace_until'].strftime('%H:%M:%S')}", "DEBUG")
    
    def is_in_grace_period(self, clone_data):
        """Check apakah clone masih dalam grace period"""
        with self.lock:
            key = self.get_clone_key(clone_data)
            
            if key not in self.states:
                return False
            
            state = self.states[key]
            now = datetime.now()
            
            if now < state['grace_until']:
                remaining = (state['grace_until'] - now).total_seconds()
                log_message(f"      ⏳ In grace period: {remaining:.0f}s remaining", "DEBUG")
                return True
            
            return False
    
    def get_restart_count(self, clone_data, window_seconds=3600):
        """Get jumlah restart dalam time window tertentu"""
        with self.lock:
            key = self.get_clone_key(clone_data)
            
            if key not in self.states:
                return 0
            
            state = self.states[key]
            now = datetime.now()
            last_restart = state.get('last_restart', now - timedelta(hours=2))
            
            if (now - last_restart).total_seconds() > window_seconds:
                return 0
            
            return state.get('restart_count', 0)
    
    def should_skip_restart(self, clone_data):
        """
        Decide apakah restart harus di-skip
        Returns: (should_skip, reason)
        """
        
        # Check grace period
        if self.is_in_grace_period(clone_data):
            return (True, "in_grace_period")
        
        # Check restart loop (lebih dari 5 restart dalam 10 menit)
        restart_count = self.get_restart_count(clone_data, window_seconds=600)
        if restart_count >= 5:
            log_message(f"      ⚠️  Too many restarts: {restart_count} in 10 minutes", "WARNING")
            return (True, "too_many_restarts")
        
        return (False, None)

# Global state manager
state_manager = StateManager()

# ═══════════════════════════════════════════════════════════════
#                    Configuration Loader
# ═══════════════════════════════════════════════════════════════

class Config:
    def __init__(self, config_file='config.json'):
        self.config_file = Path(config_file)
        self.config = self.load_config()
    
    def load_config(self):
        if not self.config_file.exists():
            print(f"❌ Config file not found: {self.config_file}")
            sys.exit(1)
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON: {e}")
            sys.exit(1)
    
    def get_all_enabled_clones(self):
        clones = []
        for account in self.config.get('accounts', []):
            if not account.get('enabled', True):
                continue
            
            for instance in account.get('instances', []):
                if not instance.get('enabled', True):
                    continue
                
                for clone in instance.get('clones', []):
                    if not clone.get('enabled', True):
                        continue
                    
                    clones.append({
                        'account_id': account['account_id'],
                        'account_name': account['account_name'],
                        'access_key_id': account['access_key_id'],
                        'secret_access_key': account['secret_access_key'],
                        'instance_pad_code': instance['pad_code'],
                        'instance_name': instance['name'],
                        'clone_name': clone['name'],
                        'clone_package': clone['package'],
                        'server_url': clone['server_url']
                    })
        
        return clones
    
    @property
    def global_settings(self):
        return self.config.get('global_settings', {})

# ═══════════════════════════════════════════════════════════════
#                    Database (Optional)
# ═══════════════════════════════════════════════════════════════

class Database:
    def __init__(self, db_file='vsphone_monitor.db'):
        self.db_file = Path(db_file)
        self.enabled = False
        self.conn = None
        self.lock = threading.Lock()
    
    def enable(self):
        try:
            import sqlite3
            self.conn = sqlite3.connect(self.db_file, check_same_thread=False)
            self.enabled = True
            self._create_tables()
            log_message(f"✅ Database enabled: {self.db_file}", "INFO")
        except:
            log_message("⚠️  Database disabled", "WARNING")
    
    def _create_tables(self):
        if not self.enabled:
            return
        
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                account_name TEXT,
                instance_name TEXT,
                clone_name TEXT,
                event_type TEXT,
                issue_type TEXT,
                success BOOLEAN,
                duration_seconds REAL,
                skip_reason TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clone_status (
                clone_key TEXT PRIMARY KEY,
                account_name TEXT,
                instance_name TEXT,
                clone_name TEXT,
                last_check DATETIME,
                is_healthy BOOLEAN,
                last_issue_type TEXT,
                total_crashes INTEGER DEFAULT 0,
                total_disconnects INTEGER DEFAULT 0,
                total_hangs INTEGER DEFAULT 0,
                total_fixes INTEGER DEFAULT 0,
                total_skipped INTEGER DEFAULT 0
            )
        ''')
        
        self.conn.commit()
    
    def log_event(self, clone_data, event_type, issue_type=None, success=None, duration=None, skip_reason=None):
        if not self.enabled:
            return
        
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT INTO events (account_name, instance_name, clone_name, 
                                      event_type, issue_type, success, duration_seconds, skip_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    clone_data['account_name'],
                    clone_data['instance_name'],
                    clone_data['clone_name'],
                    event_type,
                    issue_type,
                    success,
                    duration,
                    skip_reason
                ))
                self.conn.commit()
        except:
            pass
    
    def update_clone_status(self, clone_data, is_healthy, issue_type=None, was_skipped=False):
        if not self.enabled:
            return
        
        try:
            with self.lock:
                clone_key = f"{clone_data['account_id']}:{clone_data['instance_pad_code']}:{clone_data['clone_package']}"
                
                cursor = self.conn.cursor()
                cursor.execute('SELECT * FROM clone_status WHERE clone_key = ?', (clone_key,))
                existing = cursor.fetchone()
                
                if existing:
                    updates = []
                    
                    if issue_type == 'crash':
                        updates.append('total_crashes = total_crashes + 1')
                    elif issue_type == 'disconnect':
                        updates.append('total_disconnects = total_disconnects + 1')
                    elif issue_type == 'hang':
                        updates.append('total_hangs = total_hangs + 1')
                    
                    if not was_skipped and issue_type:
                        updates.append('total_fixes = total_fixes + 1')
                    
                    if was_skipped:
                        updates.append('total_skipped = total_skipped + 1')
                    
                    updates_str = ', '.join(updates) if updates else ''
                    
                    if updates_str:
                        cursor.execute(f'''
                            UPDATE clone_status 
                            SET last_check = ?, is_healthy = ?, last_issue_type = ?, {updates_str}
                            WHERE clone_key = ?
                        ''', (datetime.now().isoformat(), is_healthy, issue_type, clone_key))
                    else:
                        cursor.execute(f'''
                            UPDATE clone_status 
                            SET last_check = ?, is_healthy = ?, last_issue_type = ?
                            WHERE clone_key = ?
                        ''', (datetime.now().isoformat(), is_healthy, issue_type, clone_key))
                else:
                    cursor.execute('''
                        INSERT INTO clone_status (clone_key, account_name, instance_name, clone_name,
                                                 last_check, is_healthy, last_issue_type,
                                                 total_crashes, total_disconnects, total_hangs, 
                                                 total_fixes, total_skipped)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        clone_key,
                        clone_data['account_name'],
                        clone_data['instance_name'],
                        clone_data['clone_name'],
                        datetime.now().isoformat(),
                        is_healthy,
                        issue_type,
                        1 if issue_type == 'crash' else 0,
                        1 if issue_type == 'disconnect' else 0,
                        1 if issue_type == 'hang' else 0,
                        0 if was_skipped else (1 if not is_healthy else 0),
                        1 if was_skipped else 0
                    ))
                
                self.conn.commit()
        except:
            pass
    
    def get_all_clones_status(self):
        if not self.enabled:
            return []
        
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT account_name, instance_name, clone_name, last_check,
                           is_healthy, last_issue_type, total_crashes, total_disconnects, 
                           total_hangs, total_fixes, total_skipped
                    FROM clone_status
                ''')
                
                result = []
                for row in cursor.fetchall():
                    result.append({
                        'account_name': row[0],
                        'instance_name': row[1],
                        'clone_name': row[2],
                        'last_check': row[3],
                        'is_healthy': bool(row[4]) if row[4] is not None else True,
                        'last_issue_type': row[5],
                        'total_crashes': row[6] or 0,
                        'total_disconnects': row[7] or 0,
                        'total_hangs': row[8] or 0,
                        'total_fixes': row[9] or 0,
                        'total_skipped': row[10] or 0
                    })
                
                return result
        except:
            return []
    
    def close(self):
        if self.enabled and self.conn:
            self.conn.close()

db = Database()

# ═══════════════════════════════════════════════════════════════
#                    Logging
# ═══════════════════════════════════════════════════════════════

log_lock = threading.Lock()
LOG_FILE = None

def init_logging(config):
    global LOG_FILE
    LOG_FILE = Path(config.global_settings.get('log_file', 'vsphone_monitor.log'))

def log_message(message, level="INFO"):
    with log_lock:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        
        if level == "DEBUG" and not config.global_settings.get('debug_mode', False):
            return
        
        colors = {
            "DEBUG": "\033[90m",
            "INFO": "\033[0m",
            "WARNING": "\033[93m",
            "ERROR": "\033[91m",
            "SUCCESS": "\033[92m"
        }
        
        color = colors.get(level, "\033[0m")
        print(f"{color}{log_entry}\033[0m")
        
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(log_entry + '\n')
        except:
            pass

def send_telegram(message, config):
    token = config.global_settings.get('telegram_bot_token')
    chat_id = config.global_settings.get('telegram_chat_id')
    
    if not token or not chat_id:
        return
    
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=5)
    except:
        pass

# ═══════════════════════════════════════════════════════════════
#                    API Functions
# ═══════════════════════════════════════════════════════════════

def sha256_hex(data):
    return hashlib.sha256(data.encode()).hexdigest()

def hmac_sha256(key, data):
    return hmac.new(key, data.encode(), hashlib.sha256).digest()

def get_signature(body, x_date, sk):
    host = "api.vsphone.com"
    content_type = "application/json;charset=UTF-8"
    
    json_string = json.dumps(body, separators=(',', ':'), ensure_ascii=False) if body else ""
    x_content_sha256 = sha256_hex(json_string)
    
    canonical_string = (
        f"host:{host}\n"
        f"x-date:{x_date}\n"
        f"content-type:{content_type}\n"
        f"signedHeaders:content-type;host;x-content-sha256;x-date\n"
        f"x-content-sha256:{x_content_sha256}"
    )
    
    short_x_date = x_date[:8]
    service = "armcloud-paas"
    credential_scope = f"{short_x_date}/{service}/request"
    hash_sha256 = sha256_hex(canonical_string)
    
    string_to_sign = f"HMAC-SHA256\n{x_date}\n{credential_scope}\n{hash_sha256}"
    
    k_date = hmac_sha256(sk.encode(), short_x_date)
    k_service = hmac_sha256(k_date, service)
    signing_key = hmac_sha256(k_service, "request")
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    
    return signature

def make_api_request(access_key, secret_key, endpoint, body=None, timeout=15):
    x_date = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    signature = get_signature(body, x_date, secret_key)
    short_date = x_date[:8]
    
    headers = {
        'content-type': 'application/json;charset=UTF-8',
        'x-date': x_date,
        'x-host': 'api.vsphone.com',
        'authorization': f'HMAC-SHA256 Credential={access_key}/{short_date}/armcloud-paas/request, SignedHeaders=content-type;host;x-content-sha256;x-date, Signature={signature}'
    }
    
    url = f"{BASE_URL}{endpoint}"
    
    try:
        if body:
            response = requests.post(url, headers=headers, json=body, timeout=timeout)
        else:
            response = requests.get(url, headers=headers, timeout=timeout)
        
        response.raise_for_status()
        return response.json()
    except:
        return None

# ═══════════════════════════════════════════════════════════════
#     🔥 PROVEN DETECTION from v4.0
# ═══════════════════════════════════════════════════════════════

def check_for_roblox_error(access_key, secret_key, pad_code, package):
    log_message(f"      → Checking for Roblox errors...", "DEBUG")
    
    ROBLOX_ERROR_KEYWORDS = [
        "Connection Failed", "Error Code", "Failed to connect",
        "Try again", "Retry", "Disconnected", "No response from server"
    ]
    
    body = {
        "padCode": pad_code,
        "scriptContent": "dumpsys window windows | grep -A 5 'mCurrentFocus' | head -20"
    }
    
    result = make_api_request(access_key, secret_key, "/vsphone/api/padApi/syncCmd", body)
    
    if result and result.get("code") == 200:
        data = result.get("data", [])
        if data and len(data) > 0:
            window_info = data[0].get("taskResult", "").lower()
            
            for keyword in ROBLOX_ERROR_KEYWORDS:
                if keyword.lower() in window_info:
                    log_message(f"      🔥 Roblox error detected: '{keyword}'", "DEBUG")
                    return True
    
    return False

def check_app_responding(access_key, secret_key, pad_code, package):
    log_message(f"      → Checking responsiveness...", "DEBUG")
    
    body = {
        "padCode": pad_code,
        "scriptContent": f"dumpsys activity activities | grep {package} | grep -i 'mResumedActivity\\|resumed' | head -5"
    }
    
    result = make_api_request(access_key, secret_key, "/vsphone/api/padApi/syncCmd", body)
    
    if result and result.get("code") == 200:
        data = result.get("data", [])
        if data and len(data) > 0:
            activity_info = data[0].get("taskResult", "")
            if activity_info.strip() and package in activity_info:
                log_message(f"      ✅ App has resumed activity", "DEBUG")
                return True
    
    # Fallback: Check process uptime
    body2 = {
        "padCode": pad_code,
        "scriptContent": f"ps -o etime -A | grep {package} | head -1"
    }
    
    result2 = make_api_request(access_key, secret_key, "/vsphone/api/padApi/syncCmd", body2)
    
    if result2 and result2.get("code") == 200:
        data2 = result2.get("data", [])
        if data2 and len(data2) > 0:
            uptime_info = data2[0].get("taskResult", "")
            if uptime_info.strip():
                log_message(f"      ✅ Process has uptime", "DEBUG")
                return True
    
    log_message(f"      ⚠️  App not responding", "DEBUG")
    return False

def check_app_status(clone_data):
    """
    v4.0 PROVEN complete health check
    Returns: (is_healthy, issue_type)
    """
    
    access_key = clone_data['access_key_id']
    secret_key = clone_data['secret_access_key']
    pad_code = clone_data['instance_pad_code']
    package = clone_data['clone_package']
    
    log_message(f"   🔍 Checking: {clone_data['clone_name']}", "DEBUG")
    
    # Step 1: Check if process exists (CRITICAL)
    body = {
        "padCode": pad_code,
        "scriptContent": f"ps -A | grep {package} | head -1"
    }
    
    result = make_api_request(access_key, secret_key, "/vsphone/api/padApi/syncCmd", body)
    
    if not result or result.get("code") != 200:
        log_message(f"      ❌ API check failed", "DEBUG")
        return (False, "crash")
    
    data = result.get("data", [])
    if not data or len(data) == 0:
        log_message(f"      ❌ No data returned", "DEBUG")
        return (False, "crash")
    
    task_result = data[0].get("taskResult", "")
    
    # Process doesn't exist = crashed
    if package not in task_result or len(task_result.strip()) == 0:
        log_message(f"      ❌ Process not found (CRASH)", "DEBUG")
        return (False, "crash")
    
    log_message(f"      ✅ Process exists", "DEBUG")
    
    # Step 2: Check for Roblox error screens
    if check_for_roblox_error(access_key, secret_key, pad_code, package):
        return (False, "disconnect")
    
    # Step 3: Check if app is responding
    if not check_app_responding(access_key, secret_key, pad_code, package):
        return (False, "hang")
    
    # All checks passed!
    log_message(f"      ✅ HEALTHY", "DEBUG")
    return (True, None)

def execute_restart(clone_data, issue_type):
    """
    Execute restart using ADB command from config
    """
    
    access_key = clone_data['access_key_id']
    secret_key = clone_data['secret_access_key']
    pad_code = clone_data['instance_pad_code']
    package = clone_data['clone_package']
    server_url = clone_data['server_url']
    
    issue_icons = {"crash": "💥", "disconnect": "🌐", "hang": "⏸️"}
    issue_names = {"crash": "CRASH", "disconnect": "DISCONNECT", "hang": "HANG"}
    
    icon = issue_icons.get(issue_type, "⚠️")
    name = issue_names.get(issue_type, "ISSUE")
    
    log_message(f"{icon} {name} detected: {clone_data['clone_name']}")
    
    # 🔥 NEW: Check if should skip restart
    should_skip, skip_reason = state_manager.should_skip_restart(clone_data)
    
    if should_skip:
        if skip_reason == "in_grace_period":
            log_message(f"⏭️  Skipping restart: Clone in grace period (still loading)", "WARNING")
        elif skip_reason == "too_many_restarts":
            log_message(f"⏭️  Skipping restart: Too many restarts (possible persistent issue)", "WARNING")
        
        return (False, 0, f"skipped_{skip_reason}")
    
    log_message(f"🔄 Executing restart...")
    
    # Build ADB command
    adb_command = f'am start -a android.intent.action.VIEW -d "{server_url}" {package}'
    
    body = {
        "padCode": pad_code,
        "scriptContent": adb_command
    }
    
    start_time = time.time()
    result = make_api_request(access_key, secret_key, "/vsphone/api/padApi/syncCmd", body, timeout=30)
    duration = time.time() - start_time
    
    # 🔍 DEBUG: Print full response
    log_message(f"      API Response: {json.dumps(result, indent=2)}", "DEBUG")
    
    # Check response
    if result and result.get("code") == 200:
        data = result.get("data", [])
        
        # Check if command executed successfully
        if data and len(data) > 0:
            task_result = data[0].get("taskResult", "")
            status = data[0].get("status")
            
            # Log detailed result
            log_message(f"      Task Status: {status}", "DEBUG")
            log_message(f"      Task Result: {task_result[:200]}", "DEBUG")
            
            # Consider it success if API call succeeded
            # Even if app doesn't respond immediately
            grace_seconds = config.global_settings.get('grace_period_seconds', 120)
            state_manager.mark_restart(clone_data, grace_seconds)
            
            log_message(f"✅ Restart command sent to {clone_data['clone_name']} ({duration:.1f}s)", "SUCCESS")
            return (True, duration, None)
        else:
            log_message(f"⚠️  No data in response for {clone_data['clone_name']}", "WARNING")
            return (False, duration, "no_data")
    else:
        error_code = result.get("code") if result else "no_response"
        error_msg = result.get("message", "Unknown") if result else "API failed"
        
        log_message(f"❌ API Error [{error_code}]: {error_msg}", "ERROR")
        log_message(f"      Full response: {result}", "DEBUG")
        
        return (False, duration, f"{error_code}: {error_msg}")

# ═══════════════════════════════════════════════════════════════
#                    Statistics & Worker
# ═══════════════════════════════════════════════════════════════

class Statistics:
    def __init__(self):
        self.total_checks = 0
        self.total_fixed = 0
        self.total_failed = 0
        self.total_skipped = 0
        self.crashes = 0
        self.disconnects = 0
        self.hangs = 0
        self.start_time = datetime.now()
        self.lock = threading.Lock()
    
    def increment_check(self, count=1):
        with self.lock:
            self.total_checks += count
    
    def increment_fix(self, issue_type):
        with self.lock:
            self.total_fixed += 1
            if issue_type == 'crash':
                self.crashes += 1
            elif issue_type == 'disconnect':
                self.disconnects += 1
            elif issue_type == 'hang':
                self.hangs += 1
    
    def increment_failure(self):
        with self.lock:
            self.total_failed += 1
    
    def increment_skipped(self):
        with self.lock:
            self.total_skipped += 1
    
    def get_summary(self):
        uptime = datetime.now() - self.start_time
        hours = int(uptime.total_seconds() / 3600)
        minutes = int((uptime.total_seconds() % 3600) / 60)
        
        success_rate = (self.total_fixed / max(self.total_fixed + self.total_failed, 1)) * 100
        
        return f"""
╔══════════════════════════════════════════════════════════╗
║                    📊 STATISTICS                         ║
╠══════════════════════════════════════════════════════════╣
║  ⏱️  Uptime: {hours}h {minutes}m
║  🔍 Checks: {self.total_checks:,}
║  ✅ Fixed: {self.total_fixed}
║  💥 Crashes: {self.crashes}
║  🌐 Disconnects: {self.disconnects}
║  ⏸️  Hangs: {self.hangs}
║  ⏭️  Skipped: {self.total_skipped}
║  ❌ Failed: {self.total_failed}
║  📈 Success: {success_rate:.1f}%
╚══════════════════════════════════════════════════════════╝
"""

stats = Statistics()

def check_and_fix_clone(clone_data):
    clone_name = f"{clone_data['instance_name']} > {clone_data['clone_name']}"
    
    try:
        # Health check using PROVEN v4.0 method
        is_healthy, issue_type = check_app_status(clone_data)
        
        # Update database
        db.update_clone_status(clone_data, is_healthy, issue_type)
        
        if is_healthy:
            return (clone_name, 'healthy', None, 0, None)
        
        # Issue detected
        log_message(f"⚠️  {clone_name}: {issue_type.upper()}", "WARNING")
        
        # Return issue for batch processing
        return (clone_name, 'needs_fix', issue_type, 0, clone_data)
    
    except Exception as e:
        log_message(f"❌ {clone_name}: Exception - {e}", "ERROR")
        return (clone_name, 'error', None, 0, None)

def fix_clones_sequential(clones_to_fix, delay_between=2):
    """
    Fix clones sequentially with delay to prevent API overload
    """
    results = []
    
    for clone_name, issue_type, clone_data in clones_to_fix:
        log_message(f"\n🔧 Processing fix for: {clone_name}", "INFO")
        
        # Attempt fix
        success, duration, error = execute_restart(clone_data, issue_type)
        
        # Check if was skipped
        was_skipped = error and error.startswith('skipped_')
        
        # Log to database
        db.log_event(clone_data, 'restart', issue_type, success, duration, error if was_skipped else None)
        
        if was_skipped:
            stats.increment_skipped()
            log_message(f"⏭️  {clone_name}: Restart skipped ({error})", "WARNING")
            db.update_clone_status(clone_data, False, issue_type, was_skipped=True)
            results.append((clone_name, 'skipped', issue_type, duration))
        elif success:
            stats.increment_fix(issue_type)
            log_message(f"✅ {clone_name}: Fixed in {duration:.1f}s", "SUCCESS")
            results.append((clone_name, 'fixed', issue_type, duration))
        else:
            stats.increment_failure()
            log_message(f"❌ {clone_name}: Fix failed - {error}", "ERROR")
            results.append((clone_name, 'failed', issue_type, duration))
        
        # Delay between fixes to prevent API overload
        if delay_between > 0 and clone_data != clones_to_fix[-1][2]:
            log_message(f"   ⏸️  Waiting {delay_between}s before next fix...", "DEBUG")
            time.sleep(delay_between)
    
    return results

# ═══════════════════════════════════════════════════════════════
#                    Main Loop
# ═══════════════════════════════════════════════════════════════

def monitor_loop(config):
    clones = config.get_all_enabled_clones()
    
    if len(clones) == 0:
        log_message("❌ No enabled clones", "ERROR")
        sys.exit(1)
    
    grace_period = config.global_settings.get('grace_period_seconds', 120)
    fix_delay = config.global_settings.get('fix_delay_seconds', 2)
    
    log_message("=" * 60)
    log_message(f"🚀 VSPhone Monitor v{VERSION} Started")
    log_message(f"📊 Clones: {len(clones)}")
    log_message(f"⏱️  Interval: {config.global_settings.get('check_interval', 30)}s")
    log_message(f"🕐 Grace Period: {grace_period}s")
    log_message(f"⏸️  Fix Delay: {fix_delay}s")
    log_message(f"🔥 Using PROVEN v4.0 detection methods")
    log_message(f"🛡️  Restart loop protection: ENABLED")
    log_message("=" * 60)
    
    send_telegram(
        f"🚀 <b>Monitor v{VERSION} Started</b>\n"
        f"📊 {len(clones)} clones\n"
        f"🕐 Grace: {grace_period}s\n"
        f"🔥 Proven detection enabled",
        config
    )
    
    check_interval = config.global_settings.get('check_interval', 30)
    max_workers = min(10, len(clones))
    
    while True:
        try:
            cycle_start = time.time()
            stats.increment_check(len(clones))
            
            log_message(f"\n🔍 Checking {len(clones)} clones...")
            
            results = {'healthy': [], 'fixed': [], 'failed': [], 'error': [], 'skipped': []}
            issue_counts = defaultdict(int)
            clones_to_fix = []
            
            # PHASE 1: Parallel health check (fast)
            log_message("   📋 Phase 1: Health check (parallel)...", "DEBUG")
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(check_and_fix_clone, clone): clone for clone in clones}
                
                for future in as_completed(futures):
                    clone_name, status, issue_type, duration, clone_data = future.result()
                    
                    if status == 'healthy':
                        results['healthy'].append(clone_name)
                    elif status == 'needs_fix':
                        clones_to_fix.append((clone_name, issue_type, clone_data))
                    elif status == 'error':
                        results['error'].append(clone_name)
            
            log_message(f"   ✅ Health check complete: {len(results['healthy'])} healthy, {len(clones_to_fix)} need fixing", "INFO")
            
            # PHASE 2: Sequential fix (to prevent API overload)
            if clones_to_fix:
                log_message(f"\n   🔧 Phase 2: Fixing {len(clones_to_fix)} clone(s) sequentially...", "INFO")
                fix_results = fix_clones_sequential(clones_to_fix, delay_between=fix_delay)
                
                for clone_name, status, issue_type, duration in fix_results:
                    results[status].append(clone_name)
                    if status in ['fixed', 'skipped']:
                        issue_counts[issue_type] += 1
            
            cycle_duration = time.time() - cycle_start
            
            # Summary
            log_message("\n" + "─" * 60)
            log_message(f"✅ Cycle Complete ({cycle_duration:.1f}s)")
            log_message(f"   Healthy: {len(results['healthy'])}")
            
            if results['fixed']:
                log_message(f"   Fixed: {len(results['fixed'])}", "SUCCESS")
            
            if results['skipped']:
                log_message(f"   Skipped: {len(results['skipped'])} (in grace period)", "WARNING")
            
            if results['fixed'] or results['skipped']:
                issues_str = ", ".join([f"{v} {k}" for k, v in issue_counts.items()])
                log_message(f"   Issues: {issues_str}")
            
            if results['failed']:
                log_message(f"   Failed: {len(results['failed'])}", "WARNING")
            
            log_message("─" * 60)
            
            # Stats every 10 cycles
            if stats.total_checks % (10 * len(clones)) == 0:
                print(stats.get_summary())
            
            # Telegram notification
            if results['fixed'] or results['failed'] or results['skipped']:
                notification = f"📊 <b>Cycle Report</b>\n"
                notification += f"✅ Healthy: {len(results['healthy'])}\n"
                notification += f"🔧 Fixed: {len(results['fixed'])}\n"
                notification += f"⏭️ Skipped: {len(results['skipped'])}\n"
                notification += f"❌ Failed: {len(results['failed'])}"
                
                send_telegram(notification, config)
            
            log_message(f"\n💤 Waiting {check_interval}s...")
            time.sleep(check_interval)
        
        except KeyboardInterrupt:
            log_message("\n🛑 Shutdown...")
            print(stats.get_summary())
            send_telegram(f"🛑 <b>Monitor Stopped</b>\nFixes: {stats.total_fixed}\nSkipped: {stats.total_skipped}", config)
            break
        
        except Exception as e:
            log_message(f"❌ Error: {e}", "ERROR")
            time.sleep(check_interval)

# ═══════════════════════════════════════════════════════════════
#                    Web UI (Optional)
# ═══════════════════════════════════════════════════════════════

def start_web_ui(config):
    try:
        from flask import Flask, render_template_string, jsonify
        
        app = Flask(__name__)
        
        HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>VSPhone Monitor</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:sans-serif; background:linear-gradient(135deg,#667eea,#764ba2); padding:20px; }
.container { max-width:1200px; margin:0 auto; }
.header { background:white; padding:30px; border-radius:15px; box-shadow:0 10px 30px rgba(0,0,0,.2); margin-bottom:30px; text-align:center; }
.header h1 { color:#667eea; font-size:2.5em; }
.stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:20px; margin-bottom:30px; }
.stat-card { background:white; padding:25px; border-radius:15px; box-shadow:0 5px 15px rgba(0,0,0,.1); text-align:center; }
.stat-icon { font-size:3em; }
.stat-value { font-size:2.5em; font-weight:bold; color:#667eea; }
.stat-label { color:#666; }
.clones-section { background:white; padding:30px; border-radius:15px; box-shadow:0 10px 30px rgba(0,0,0,.2); }
.clones-section h2 { color:#667eea; margin-bottom:20px; }
table { width:100%; border-collapse:collapse; }
th { background:#667eea; color:white; padding:15px; text-align:left; }
td { padding:15px; border-bottom:1px solid #eee; }
tr:hover { background:#f8f9ff; }
.badge { padding:5px 15px; border-radius:20px; font-size:0.9em; font-weight:600; }
.badge-ok { background:#d4edda; color:#155724; }
.badge-warn { background:#fff3cd; color:#856404; }
.last-update { text-align:center; color:white; margin-top:20px; }
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>🚀 VSPhone Monitor v5.3.1</h1>
        <p>🛡️ With Restart Loop Protection</p>
    </div>
    
    <div class="stats">
        <div class="stat-card">
            <div class="stat-icon">📊</div>
            <div class="stat-value" id="total">-</div>
            <div class="stat-label">Total Clones</div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">✅</div>
            <div class="stat-value" id="healthy">-</div>
            <div class="stat-label">Healthy</div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">🔧</div>
            <div class="stat-value" id="fixes">-</div>
            <div class="stat-label">Total Fixes</div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">⏭️</div>
            <div class="stat-value" id="skipped">-</div>
            <div class="stat-label">Skipped</div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">⚡</div>
            <div class="stat-value" id="rate">-</div>
            <div class="stat-label">Success Rate</div>
        </div>
    </div>
    
    <div class="clones-section">
        <h2>Clone Status</h2>
        <div id="content">Loading...</div>
    </div>
    
    <div class="last-update" id="update">Last updated: -</div>
</div>

<script>
async function load() {
    try {
        const r = await fetch('/api/status');
        const d = await r.json();
        
        document.getElementById('total').textContent = d.total;
        document.getElementById('healthy').textContent = d.healthy;
        document.getElementById('fixes').textContent = d.fixes;
        document.getElementById('skipped').textContent = d.skipped;
        document.getElementById('rate').textContent = d.rate + '%';
        
        let html = '<table><thead><tr><th>Account</th><th>Instance</th><th>Clone</th><th>Status</th><th>Crashes</th><th>Disconnects</th><th>Hangs</th><th>Fixes</th><th>Skipped</th></tr></thead><tbody>';
        
        if (d.clones.length === 0) {
            html += '<tr><td colspan="9" style="text-align:center;padding:40px;">No clones</td></tr>';
        } else {
            d.clones.forEach(c => {
                const badge = c.is_healthy ? 'badge-ok' : 'badge-warn';
                const status = c.is_healthy ? '✅ Healthy' : '⚠️ ' + (c.last_issue_type || 'Issue');
                html += `<tr>
                    <td>${c.account_name}</td>
                    <td>${c.instance_name}</td>
                    <td>${c.clone_name}</td>
                    <td><span class="badge ${badge}">${status}</span></td>
                    <td>${c.total_crashes}</td>
                    <td>${c.total_disconnects}</td>
                    <td>${c.total_hangs}</td>
                    <td>${c.total_fixes}</td>
                    <td>${c.total_skipped || 0}</td>
                </tr>`;
            });
        }
        
        html += '</tbody></table>';
        document.getElementById('content').innerHTML = html;
        document.getElementById('update').textContent = 'Last updated: ' + new Date().toLocaleTimeString();
    } catch(e) {
        console.error(e);
    }
}

load();
setInterval(load, 10000);
</script>
</body>
</html>"""
        
        @app.route('/')
        def index():
            return render_template_string(HTML)
        
        @app.route('/api/status')
        def api_status():
            try:
                clones = config.get_all_enabled_clones()
                clone_statuses = db.get_all_clones_status() if db.enabled else []
                
                if not clone_statuses:
                    clone_statuses = [
                        {
                            'account_name': c.get('account_name', c['account_id']),
                            'instance_name': c['instance_name'],
                            'clone_name': c['clone_name'],
                            'is_healthy': True,
                            'last_issue_type': None,
                            'total_crashes': 0,
                            'total_disconnects': 0,
                            'total_hangs': 0,
                            'total_fixes': 0,
                            'total_skipped': 0
                        }
                        for c in clones
                    ]
                
                total = len(clone_statuses)
                healthy = sum(1 for c in clone_statuses if c.get('is_healthy', True))
                fixes = stats.total_fixed
                skipped = stats.total_skipped
                failed = stats.total_failed
                rate = round((fixes / max(fixes + failed, 1)) * 100, 1)
                
                return jsonify({
                    'total': total,
                    'healthy': healthy,
                    'fixes': fixes,
                    'skipped': skipped,
                    'rate': rate,
                    'clones': clone_statuses
                })
            except Exception as e:
                return jsonify({'error': str(e), 'total': 0, 'healthy': 0, 'fixes': 0, 'skipped': 0, 'rate': 0, 'clones': []}), 200
        
        def run():
            log_message("🌐 Web UI: http://localhost:5000", "INFO")
            app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
        
        threading.Thread(target=run, daemon=True).start()
        log_message("✅ Web UI started", "SUCCESS")
        time.sleep(2)
    except:
        log_message("⚠️  Web UI disabled (Flask not installed)", "WARNING")

# ═══════════════════════════════════════════════════════════════
#                    Main Entry Point
# ═══════════════════════════════════════════════════════════════

def print_banner():
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║      VSPhone Monitor v{VERSION}                        ║
║           🛡️ RESTART LOOP PROTECTION ENABLED                ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  ✅ PROVEN v4.0 Detection Methods                            ║
║  ✅ State Tracking (persists across restarts)                ║
║  ✅ Grace Period (default: 120s)                             ║
║  ✅ Anti-Loop Protection                                     ║
║                                                              ║
║  🔧 FIXES:                                                   ║
║     • Clone won't restart if in grace period                 ║
║     • State persists when script restarts                    ║
║     • Prevents restart loops (max 5 in 10 min)               ║
║                                                              ║
║  📚 USAGE:                                                   ║
║     python monitor.py                                        ║
║     python monitor.py --grace 180  (3 min grace)             ║
║     python monitor.py --database --web-ui                    ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")

def main():
    global config
    
    parser = argparse.ArgumentParser(description='VSPhone Monitor v5.3.1')
    parser.add_argument('--config', default='config.json', help='Config file')
    parser.add_argument('--database', action='store_true', help='Enable database')
    parser.add_argument('--web-ui', action='store_true', help='Enable web UI')
    parser.add_argument('--debug', action='store_true', help='Debug mode')
    parser.add_argument('--grace', type=int, help='Grace period in seconds (default: 120)')
    
    args = parser.parse_args()
    
    print_banner()
    
    print("🔍 Loading configuration...")
    config = Config(args.config)
    
    if args.debug:
        config.config['global_settings']['debug_mode'] = True
    
    if args.grace:
        config.config['global_settings']['grace_period_seconds'] = args.grace
    
    # Set default grace period if not in config
    if 'grace_period_seconds' not in config.config['global_settings']:
        config.config['global_settings']['grace_period_seconds'] = 120
    
    # Set default fix delay if not in config
    if 'fix_delay_seconds' not in config.config['global_settings']:
        config.config['global_settings']['fix_delay_seconds'] = 2
    
    init_logging(config)
    log_message("✅ Configuration loaded", "SUCCESS")
    
    clones = config.get_all_enabled_clones()
    grace_period = config.global_settings.get('grace_period_seconds', 120)
    fix_delay = config.global_settings.get('fix_delay_seconds', 2)
    
    print(f"\n📋 Configuration:")
    print(f"   Clones: {len(clones)}")
    print(f"   Interval: {config.global_settings.get('check_interval', 30)}s")
    print(f"   Grace Period: {grace_period}s")
    print(f"   Fix Delay: {fix_delay}s (between restarts)")
    print(f"   Database: {'✅' if args.database else '❌'}")
    print(f"   Web UI: {'✅' if args.web_ui else '❌'}")
    print(f"   Debug: {'✅' if args.debug else '❌'}")
    print(f"   🔥 Detection: v4.0 PROVEN methods")
    print(f"   🛡️ Loop Protection: ENABLED")
    print()
    
    if args.database:
        db.enable()
    
    if args.web_ui:
        start_web_ui(config)
    
    try:
        import requests
    except ImportError:
        print("❌ ERROR: 'requests' not found")
        print("   Install: pip install requests")
        sys.exit(1)
    
    print("=" * 60)
    print("🚀 Starting monitoring...")
    print("=" * 60)
    print("\n💡 Tips:")
    print("   • Press Ctrl+C to stop")
    if args.web_ui:
        print("   • Dashboard: http://localhost:5000")
    print(f"   • Grace period: {grace_period}s after each restart")
    print("   • Clones in grace period will NOT be restarted")
    print("   • State persists across script restarts")
    print()
    
    try:
        monitor_loop(config)
    except Exception as e:
        log_message(f"💀 Fatal: {e}", "ERROR")
        if args.debug:
            import traceback
            log_message(traceback.format_exc(), "DEBUG")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    import signal
    
    def signal_handler(sig, frame):
        print("\n")
        log_message("Terminating...", "INFO")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    main()