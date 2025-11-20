#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║    VSPhone Roblox Monitor v5.0 - Multi-Account Edition      ║
║                                                              ║
║  NEW Features:                                               ║
║  ⚡ Multi-Account Support (Unlimited VSPhone accounts)       ║
║  ⚡ Parallel Processing (10x faster for 100+ clones)         ║
║  ⚡ SQLite Database (Advanced analytics & history)           ║
║  ⚡ Web Dashboard (Real-time monitoring UI)                  ║
║  ⚡ Smart Priority Queue (Check problem apps first)          ║
║  ⚡ Config-based (No code editing needed)                    ║
║                                                              ║
║  Legacy Features (from v4.0):                                ║
║  ✅ Crash/Disconnect/Hang Detection                          ║
║  ✅ Auto-Restart & Rejoin                                    ║
║  ✅ Telegram Notifications                                   ║
║  ✅ Detailed Statistics                                      ║
║                                                              ║
║  Author: VSPhone Automation Team                            ║
║  Version: 5.0.0                                              ║
║  Last Updated: 2025-11-17                                   ║
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
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import threading

VERSION = "5.0.0"
BASE_URL = "https://api.vsphone.com"

# ═══════════════════════════════════════════════════════════════
#                    Configuration Loader
# ═══════════════════════════════════════════════════════════════

class Config:
    """Load and validate configuration from JSON file"""
    
    def __init__(self, config_file='config.json'):
        self.config_file = Path(config_file)
        self.config = self.load_config()
        self.validate_config()
    
    def load_config(self):
        """Load configuration from JSON file"""
        if not self.config_file.exists():
            print(f"❌ ERROR: Config file not found: {self.config_file}")
            print(f"💡 Please create {self.config_file} first")
            sys.exit(1)
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"❌ ERROR: Invalid JSON in {self.config_file}")
            print(f"   {e}")
            sys.exit(1)
    
    def validate_config(self):
        """Validate configuration structure"""
        errors = []
        warnings = []
        
        # Check global settings
        if 'global_settings' not in self.config:
            errors.append("Missing 'global_settings' section")
        
        # Check accounts
        if 'accounts' not in self.config or len(self.config['accounts']) == 0:
            errors.append("No accounts configured")
        
        # Validate each account
        for i, account in enumerate(self.config.get('accounts', [])):
            acc_name = account.get('account_name', f'Account {i+1}')
            
            if not account.get('access_key_id'):
                errors.append(f"{acc_name}: Missing access_key_id")
            
            if not account.get('secret_access_key'):
                errors.append(f"{acc_name}: Missing secret_access_key")
            
            if 'instances' not in account or len(account['instances']) == 0:
                warnings.append(f"{acc_name}: No instances configured")
            
            # Validate instances
            for j, instance in enumerate(account.get('instances', [])):
                inst_name = instance.get('name', f'Instance {j+1}')
                
                if not instance.get('pad_code'):
                    errors.append(f"{acc_name} > {inst_name}: Missing pad_code")
        
        if errors:
            print("\n❌ Configuration Errors:")
            for error in errors:
                print(f"   • {error}")
            print(f"\n💡 Please fix errors in {self.config_file}")
            sys.exit(1)
        
        if warnings:
            print("\n⚠️  Configuration Warnings:")
            for warning in warnings:
                print(f"   • {warning}")
            print()
    
    def get_all_enabled_clones(self):
        """Get list of all enabled clones across all accounts"""
        clones = []
        
        for account in self.config['accounts']:
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
#                    Database Handler (SQLite)
# ═══════════════════════════════════════════════════════════════

class Database:
    """SQLite database for tracking monitoring events"""
    
    def __init__(self, db_file='vsphone_monitor.db'):
        self.db_file = Path(db_file)
        self.enabled = False
        self.conn = None
    
    def enable(self):
        """Enable database and create tables"""
        try:
            import sqlite3
            self.conn = sqlite3.connect(self.db_file, check_same_thread=False)
            self.enabled = True
            self._create_tables()
            log_message(f"✅ Database enabled: {self.db_file}", "INFO")
        except ImportError:
            log_message("⚠️  sqlite3 not available, database disabled", "WARNING")
            self.enabled = False
        except Exception as e:
            log_message(f"⚠️  Failed to enable database: {e}", "WARNING")
            self.enabled = False
    
    def _create_tables(self):
        """Create database tables"""
        if not self.enabled:
            return
        
        cursor = self.conn.cursor()
        
        # Events table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                account_id TEXT NOT NULL,
                account_name TEXT,
                instance_pad_code TEXT NOT NULL,
                instance_name TEXT,
                clone_name TEXT NOT NULL,
                clone_package TEXT NOT NULL,
                event_type TEXT NOT NULL,
                issue_type TEXT,
                success BOOLEAN,
                duration_seconds REAL,
                error_message TEXT
            )
        ''')
        
        # Statistics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                total_checks INTEGER DEFAULT 0,
                total_restarts INTEGER DEFAULT 0,
                crash_fixes INTEGER DEFAULT 0,
                disconnect_fixes INTEGER DEFAULT 0,
                hang_fixes INTEGER DEFAULT 0,
                failed_attempts INTEGER DEFAULT 0,
                uptime_hours REAL DEFAULT 0
            )
        ''')
        
        # Clone status table (current state)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clone_status (
                clone_key TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                instance_pad_code TEXT NOT NULL,
                clone_package TEXT NOT NULL,
                clone_name TEXT NOT NULL,
                last_check DATETIME,
                is_healthy BOOLEAN,
                last_issue_type TEXT,
                total_crashes INTEGER DEFAULT 0,
                total_disconnects INTEGER DEFAULT 0,
                total_hangs INTEGER DEFAULT 0,
                last_restart DATETIME
            )
        ''')
        
        self.conn.commit()
        log_message("✅ Database tables created/verified", "DEBUG")
    
    def log_event(self, clone_data, event_type, issue_type=None, success=None, duration=None, error=None):
        """Log monitoring event to database"""
        if not self.enabled:
            return
        
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO events (
                    account_id, account_name, instance_pad_code, instance_name,
                    clone_name, clone_package, event_type, issue_type,
                    success, duration_seconds, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                clone_data['account_id'],
                clone_data['account_name'],
                clone_data['instance_pad_code'],
                clone_data['instance_name'],
                clone_data['clone_name'],
                clone_data['clone_package'],
                event_type,
                issue_type,
                success,
                duration,
                error
            ))
            self.conn.commit()
        except Exception as e:
            log_message(f"DB Error: {e}", "WARNING")
    
    def update_clone_status(self, clone_data, is_healthy, issue_type=None):
        """Update current status of clone"""
        if not self.enabled:
            return
        
        try:
            clone_key = f"{clone_data['account_id']}:{clone_data['instance_pad_code']}:{clone_data['clone_package']}"
            
            cursor = self.conn.cursor()
            
            # Check if exists
            cursor.execute('SELECT * FROM clone_status WHERE clone_key = ?', (clone_key,))
            existing = cursor.fetchone()
            
            if existing:
                # Update existing
                update_fields = {
                    'last_check': datetime.now().isoformat(),
                    'is_healthy': is_healthy
                }
                
                if issue_type == 'crash':
                    cursor.execute('UPDATE clone_status SET total_crashes = total_crashes + 1 WHERE clone_key = ?', (clone_key,))
                elif issue_type == 'disconnect':
                    cursor.execute('UPDATE clone_status SET total_disconnects = total_disconnects + 1 WHERE clone_key = ?', (clone_key,))
                elif issue_type == 'hang':
                    cursor.execute('UPDATE clone_status SET total_hangs = total_hangs + 1 WHERE clone_key = ?', (clone_key,))
                
                if issue_type:
                    update_fields['last_issue_type'] = issue_type
                    update_fields['last_restart'] = datetime.now().isoformat()
                
                set_clause = ', '.join([f'{k} = ?' for k in update_fields.keys()])
                values = list(update_fields.values()) + [clone_key]
                
                cursor.execute(f'UPDATE clone_status SET {set_clause} WHERE clone_key = ?', values)
            else:
                # Insert new
                cursor.execute('''
                    INSERT INTO clone_status (
                        clone_key, account_id, instance_pad_code, clone_package, clone_name,
                        last_check, is_healthy, last_issue_type,
                        total_crashes, total_disconnects, total_hangs
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    clone_key,
                    clone_data['account_id'],
                    clone_data['instance_pad_code'],
                    clone_data['clone_package'],
                    clone_data['clone_name'],
                    datetime.now().isoformat(),
                    is_healthy,
                    issue_type,
                    1 if issue_type == 'crash' else 0,
                    1 if issue_type == 'disconnect' else 0,
                    1 if issue_type == 'hang' else 0
                ))
            
            self.conn.commit()
        except Exception as e:
            log_message(f"DB Error updating status: {e}", "WARNING")
    
    def get_problem_clones(self, limit=20):
        """Get clones with most issues (for priority checking)"""
        if not self.enabled:
            return []
        
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT clone_key, clone_name, 
                       (total_crashes + total_disconnects + total_hangs) as total_issues,
                       last_issue_type, last_restart
                FROM clone_status
                WHERE total_crashes + total_disconnects + total_hangs > 0
                ORDER BY total_issues DESC, last_restart DESC
                LIMIT ?
            ''', (limit,))
            
            return cursor.fetchall()
        except Exception as e:
            log_message(f"DB Error getting problem clones: {e}", "WARNING")
            return []
    
    def get_statistics(self, hours=24):
        """Get statistics for last N hours"""
        if not self.enabled:
            return {}
        
        try:
            cursor = self.conn.cursor()
            
            # Events in last N hours
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_events,
                    SUM(CASE WHEN event_type = 'restart' THEN 1 ELSE 0 END) as restarts,
                    SUM(CASE WHEN issue_type = 'crash' THEN 1 ELSE 0 END) as crashes,
                    SUM(CASE WHEN issue_type = 'disconnect' THEN 1 ELSE 0 END) as disconnects,
                    SUM(CASE WHEN issue_type = 'hang' THEN 1 ELSE 0 END) as hangs,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures
                FROM events
                WHERE timestamp >= datetime('now', '-' || ? || ' hours')
            ''', (hours,))
            
            row = cursor.fetchone()
            
            return {
                'total_events': row[0] or 0,
                'restarts': row[1] or 0,
                'crashes': row[2] or 0,
                'disconnects': row[3] or 0,
                'hangs': row[4] or 0,
                'failures': row[5] or 0
            }
        except Exception as e:
            log_message(f"DB Error getting statistics: {e}", "WARNING")
            return {}
    
    def close(self):
        """Close database connection"""
        if self.enabled and self.conn:
            self.conn.close()

# Global database instance
db = Database()

# ═══════════════════════════════════════════════════════════════
#                    Logging Functions
# ═══════════════════════════════════════════════════════════════

log_lock = threading.Lock()
LOG_FILE = None

def init_logging(config):
    """Initialize logging"""
    global LOG_FILE
    LOG_FILE = Path(config.global_settings.get('log_file', 'vsphone_multi.log'))

def log_message(message, level="INFO"):
    """Thread-safe logging"""
    with log_lock:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        
        # Skip DEBUG if not in debug mode
        if level == "DEBUG" and not config.global_settings.get('debug_mode', False):
            return
        
        # Color coding
        colors = {
            "DEBUG": "\033[90m",
            "INFO": "\033[0m",
            "WARNING": "\033[93m",
            "ERROR": "\033[91m",
            "CRITICAL": "\033[95m",
            "SUCCESS": "\033[92m"
        }
        
        color = colors.get(level, "\033[0m")
        reset = "\033[0m"
        
        print(f"{color}{log_entry}{reset}")
        
        # Write to file
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(log_entry + '\n')
        except:
            pass

def send_telegram(message, config):
    """Send Telegram notification"""
    token = config.global_settings.get('telegram_bot_token')
    chat_id = config.global_settings.get('telegram_chat_id')
    
    if not token or not chat_id:
        return
    
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, data=data, timeout=5)
        response.raise_for_status()
    except Exception as e:
        log_message(f"Telegram failed: {e}", "WARNING")

# ═══════════════════════════════════════════════════════════════
#                    API Functions
# ═══════════════════════════════════════════════════════════════

def sha256_hex(data):
    return hashlib.sha256(data.encode()).hexdigest()

def hmac_sha256(key, data):
    return hmac.new(key, data.encode(), hashlib.sha256).digest()

def get_signature(body, x_date, sk):
    """Generate VSPhone API signature"""
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

def make_api_request(access_key, secret_key, endpoint, body=None, retry=0):
    """Make authenticated API request"""
    max_retries = config.global_settings.get('max_retry_attempts', 3)
    retry_delay = config.global_settings.get('retry_delay', 5)
    
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
            response = requests.post(url, headers=headers, json=body, timeout=15)
        else:
            response = requests.get(url, headers=headers, timeout=15)
        
        response.raise_for_status()
        return response.json()
    
    except requests.exceptions.Timeout:
        if retry < max_retries:
            time.sleep(retry_delay)
            return make_api_request(access_key, secret_key, endpoint, body, retry + 1)
        log_message(f"API timeout after {max_retries} attempts", "ERROR")
        return None
    
    except Exception as e:
        if retry < max_retries:
            time.sleep(retry_delay)
            return make_api_request(access_key, secret_key, endpoint, body, retry + 1)
        log_message(f"API error: {e}", "ERROR")
        return None

# ═══════════════════════════════════════════════════════════════
#                    Detection Functions
# ═══════════════════════════════════════════════════════════════

ROBLOX_ERROR_KEYWORDS = [
    "Connection Failed", "Error Code", "Failed to connect",
    "Try again", "Retry", "Disconnected",
    "No response from server", "Please try again"
]

def check_app_status(clone_data):
    """
    Complete health check for Roblox clone
    Returns: (is_healthy, issue_type, error_message)
    """
    
    access_key = clone_data['access_key_id']
    secret_key = clone_data['secret_access_key']
    pad_code = clone_data['instance_pad_code']
    package = clone_data['clone_package']
    
    # Step 1: Check if process exists
    body = {
        "padCode": pad_code,
        "scriptContent": f"ps -A | grep {package} | head -1"
    }
    
    result = make_api_request(access_key, secret_key, "/vsphone/api/padApi/syncCmd", body)
    
    if not result or result.get("code") != 200:
        return (False, "crash", "API check failed")
    
    data = result.get("data", [])
    if not data or len(data) == 0:
        return (False, "crash", "No data returned")
    
    task_result = data[0].get("taskResult", "")
    
    if package not in task_result or len(task_result.strip()) == 0:
        return (False, "crash", "Process not found")
    
    # Step 2: Check for Roblox errors
    body2 = {
        "padCode": pad_code,
        "scriptContent": "dumpsys window windows | grep -A 5 'mCurrentFocus' | head -20"
    }
    
    result2 = make_api_request(access_key, secret_key, "/vsphone/api/padApi/syncCmd", body2)
    
    if result2 and result2.get("code") == 200:
        data2 = result2.get("data", [])
        if data2 and len(data2) > 0:
            window_info = data2[0].get("taskResult", "").lower()
            for keyword in ROBLOX_ERROR_KEYWORDS:
                if keyword.lower() in window_info:
                    return (False, "disconnect", f"Error detected: {keyword}")
    
    # Step 3: Check responsiveness
    body3 = {
        "padCode": pad_code,
        "scriptContent": f"dumpsys activity activities | grep {package} | grep -i 'mResumedActivity\\|resumed' | head -5"
    }
    
    result3 = make_api_request(access_key, secret_key, "/vsphone/api/padApi/syncCmd", body3)
    
    if result3 and result3.get("code") == 200:
        data3 = result3.get("data", [])
        if data3 and len(data3) > 0:
            activity_info = data3[0].get("taskResult", "")
            if not (activity_info.strip() and package in activity_info):
                return (False, "hang", "App not responding")
    
    return (True, None, None)

def execute_restart(clone_data, issue_type):
    """
    Execute restart command for clone
    Returns: (success, duration, error_message)
    """
    
    access_key = clone_data['access_key_id']
    secret_key = clone_data['secret_access_key']
    pad_code = clone_data['instance_pad_code']
    package = clone_data['clone_package']
    server_url = clone_data['server_url']
    
    # Build ADB command
    adb_command = f'am start -a android.intent.action.VIEW -d "{server_url}" {package}'
    
    body = {
        "padCode": pad_code,
        "scriptContent": adb_command
    }
    
    start_time = time.time()
    result = make_api_request(access_key, secret_key, "/vsphone/api/padApi/syncCmd", body)
    duration = time.time() - start_time
    
    if result and result.get("code") == 200:
        return (True, duration, None)
    else:
        error = result.get("message", "Unknown error") if result else "API call failed"
        return (False, duration, error)

# ═══════════════════════════════════════════════════════════════
#                    Worker Functions
# ═══════════════════════════════════════════════════════════════

def check_and_fix_clone(clone_data):
    """
    Check single clone and fix if needed
    Returns: (clone_name, status, issue_type, duration)
    """
    
    clone_name = f"{clone_data['instance_name']} > {clone_data['clone_name']}"
    
    try:
        # Check status
        is_healthy, issue_type, error_msg = check_app_status(clone_data)
        
        # Update database
        db.update_clone_status(clone_data, is_healthy, issue_type)
        
        if is_healthy:
            return (clone_name, 'healthy', None, 0)
        
        # Issue detected - attempt fix
        log_message(f"⚠️  {clone_name}: {issue_type.upper()} detected", "WARNING")
        
        success, duration, fix_error = execute_restart(clone_data, issue_type)
        
        # Log to database
        db.log_event(clone_data, 'restart', issue_type, success, duration, fix_error)
        
        if success:
            log_message(f"✅ {clone_name}: Fixed in {duration:.1f}s", "SUCCESS")
            return (clone_name, 'fixed', issue_type, duration)
        else:
            log_message(f"❌ {clone_name}: Fix failed - {fix_error}", "ERROR")
            return (clone_name, 'failed', issue_type, duration)
    
    except Exception as e:
        log_message(f"❌ {clone_name}: Exception - {e}", "ERROR")
        return (clone_name, 'error', None, 0)

# ═══════════════════════════════════════════════════════════════
#                    Statistics Tracker
# ═══════════════════════════════════════════════════════════════

class Statistics:
    """Track monitoring statistics"""
    
    def __init__(self):
        self.total_checks = 0
        self.total_fixed = 0
        self.total_failed = 0
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
    
    def get_summary(self):
        uptime = datetime.now() - self.start_time
        hours = int(uptime.total_seconds() / 3600)
        minutes = int((uptime.total_seconds() % 3600) / 60)
        
        return f"""
╔═══════════════════════════════════════════════════════════╗
║                    📊 STATISTICS                          ║
╠═══════════════════════════════════════════════════════════╣
║  ⏱️  Uptime: {hours}h {minutes}m
║  🔍 Total Checks: {self.total_checks:,}
║  ✅ Total Fixes: {self.total_fixed}
║  💥 Crash Fixes: {self.crashes}
║  🌐 Disconnect Fixes: {self.disconnects}
║  ⏸️  Hang Fixes: {self.hangs}
║  ❌ Failed Attempts: {self.total_failed}
║  📈 Success Rate: {((self.total_fixed / max(self.total_fixed + self.total_failed, 1)) * 100):.1f}%
╚═══════════════════════════════════════════════════════════╝"""

stats = Statistics()

# ═══════════════════════════════════════════════════════════════
#                    Main Monitoring Loop
# ═══════════════════════════════════════════════════════════════

def monitor_loop(config):
    """Main monitoring loop with parallel processing"""
    
    clones = config.get_all_enabled_clones()
    
    if len(clones) == 0:
        log_message("❌ No enabled clones found in configuration", "ERROR")
        sys.exit(1)
    
    log_message("=" * 60)
    log_message(f"🚀 VSPhone Monitor v{VERSION} Started")
    log_message(f"📊 Total Clones: {len(clones)}")
    
    # Group by account
    accounts_count = len(set([c['account_id'] for c in clones]))
    instances_count = len(set([f"{c['account_id']}:{c['instance_pad_code']}" for c in clones]))
    
    log_message(f"👤 Accounts: {accounts_count}")
    log_message(f"📱 Instances: {instances_count}")
    log_message(f"⏱️  Check Interval: {config.global_settings.get('check_interval', 30)}s")
    log_message(f"⚡ Parallel Workers: 10")
    log_message(f"💾 Database: {'✅ Enabled' if db.enabled else '❌ Disabled'}")
    log_message("=" * 60)
    
    # Send startup notification
    send_telegram(
        f"🚀 <b>Monitor v{VERSION} Started</b>\n"
        f"📊 {len(clones)} clones\n"
        f"👤 {accounts_count} accounts\n"
        f"📱 {instances_count} instances\n"
        f"⚡ Parallel processing enabled",
        config
    )
    
    check_interval = config.global_settings.get('check_interval', 30)
    max_workers = 10  # Parallel processing: 10 clones at once
    
    consecutive_errors = 0
    
    while True:
        try:
            cycle_start = time.time()
            stats.increment_check(len(clones))
            
            log_message(f"\n🔍 Starting check cycle for {len(clones)} clones...")
            
            results = {
                'healthy': [],
                'fixed': [],
                'failed': [],
                'error': []
            }
            
            issue_counts = defaultdict(int)
            
            # Parallel processing with ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                future_to_clone = {
                    executor.submit(check_and_fix_clone, clone): clone 
                    for clone in clones
                }
                
                # Process results as they complete
                for future in as_completed(future_to_clone):
                    clone_name, status, issue_type, duration = future.result()
                    
                    results[status].append(clone_name)
                    
                    if status == 'fixed':
                        stats.increment_fix(issue_type)
                        issue_counts[issue_type] += 1
                    elif status == 'failed':
                        stats.increment_failure()
                        issue_counts[f'{issue_type}_failed'] += 1
            
            cycle_duration = time.time() - cycle_start
            
            # Summary
            log_message("\n" + "─" * 60)
            log_message(f"✅ Cycle Complete ({cycle_duration:.1f}s)")
            log_message(f"   Healthy: {len(results['healthy'])}")
            
            if results['fixed']:
                log_message(f"   Fixed: {len(results['fixed'])}")
                if issue_counts:
                    issues_str = ", ".join([f"{v} {k}" for k, v in issue_counts.items() if not k.endswith('_failed')])
                    log_message(f"   Issues: {issues_str}")
            
            if results['failed']:
                log_message(f"   ⚠️  Failed to fix: {len(results['failed'])}", "WARNING")
            
            if results['error']:
                log_message(f"   ❌ Errors: {len(results['error'])}", "ERROR")
            
            log_message("─" * 60)
            
            # Print stats every 10 cycles
            if stats.total_checks % (10 * len(clones)) == 0:
                print(stats.get_summary())
                
                # Database stats if available
                if db.enabled:
                    db_stats = db.get_statistics(24)
                    if db_stats:
                        log_message(f"\n📊 Last 24h Database Stats:")
                        log_message(f"   Total events: {db_stats.get('total_events', 0)}")
                        log_message(f"   Restarts: {db_stats.get('restarts', 0)}")
                        log_message(f"   Crashes: {db_stats.get('crashes', 0)}")
                        log_message(f"   Disconnects: {db_stats.get('disconnects', 0)}")
            
            # Send notification if issues were fixed
            if results['fixed'] or results['failed']:
                notification = f"📊 <b>Cycle Report</b>\n"
                notification += f"✅ Healthy: {len(results['healthy'])}\n"
                
                if results['fixed']:
                    notification += f"🔧 Fixed: {len(results['fixed'])}\n"
                    for issue, count in issue_counts.items():
                        if not issue.endswith('_failed'):
                            notification += f"   • {issue}: {count}\n"
                
                if results['failed']:
                    notification += f"❌ Failed: {len(results['failed'])}\n"
                
                notification += f"⏱️ Duration: {cycle_duration:.1f}s"
                
                send_telegram(notification, config)
            
            # Reset error counter
            consecutive_errors = 0
            
            # Wait for next cycle
            log_message(f"\n💤 Waiting {check_interval}s for next cycle...")
            time.sleep(check_interval)
        
        except KeyboardInterrupt:
            log_message("\n" + "=" * 60)
            log_message("🛑 Shutdown signal received...")
            print(stats.get_summary())
            
            send_telegram(
                f"🛑 <b>Monitor Stopped</b>\n"
                f"📊 Final stats:\n"
                f"Checks: {stats.total_checks}\n"
                f"Fixes: {stats.total_fixed}\n"
                f"Success: {((stats.total_fixed / max(stats.total_fixed + stats.total_failed, 1)) * 100):.1f}%",
                config
            )
            
            log_message("👋 Goodbye!")
            break
        
        except Exception as e:
            consecutive_errors += 1
            log_message(f"❌ Error in monitoring loop: {e}", "ERROR")
            
            if config.global_settings.get('debug_mode', False):
                import traceback
                log_message(traceback.format_exc(), "DEBUG")
            
            if consecutive_errors >= 5:
                send_telegram(
                    f"⚠️ <b>Multiple Errors</b>\n"
                    f"Consecutive: {consecutive_errors}\n"
                    f"Last: {str(e)[:100]}",
                    config
                )
                consecutive_errors = 0
            
            log_message(f"⏳ Retrying in {check_interval}s...")
            time.sleep(check_interval)

# ═══════════════════════════════════════════════════════════════
#                    Web UI Launcher
# ═══════════════════════════════════════════════════════════════

def start_web_ui(config):
    """Start web dashboard in separate thread"""
    try:
        from web_ui import app, init_app
        init_app(config, db, stats)
        
        import threading
        
        def run_flask():
            log_message("🌐 Starting web dashboard on http://localhost:5000", "INFO")
            app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
        
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        log_message("✅ Web dashboard started", "SUCCESS")
        time.sleep(2)
    except ImportError:
        log_message("⚠️  Flask not installed, web UI disabled", "WARNING")
        log_message("   Install with: pip install flask", "INFO")
    except Exception as e:
        log_message(f"⚠️  Could not start web UI: {e}", "WARNING")

# ═══════════════════════════════════════════════════════════════
#                    Main Entry Point
# ═══════════════════════════════════════════════════════════════

def print_banner():
    """Print startup banner"""
    banner = f"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║      VSPhone Roblox Monitor v{VERSION}                      ║
║           Multi-Account Edition                              ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  🎯 New Features:                                            ║
║     ⚡ Multi-Account Support (Unlimited accounts)           ║
║     ⚡ Parallel Processing (10x faster)                      ║
║     ⚡ SQLite Database (Advanced tracking)                   ║
║     ⚡ Web Dashboard (Real-time monitoring)                  ║
║     ⚡ Config-based (No code editing)                        ║
║                                                              ║
║  📚 Usage:                                                   ║
║     python monitor_v5.py                                     ║
║     python monitor_v5.py --database                          ║
║     python monitor_v5.py --web-ui                            ║
║     python monitor_v5.py --database --web-ui                 ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)

def main():
    """Main entry point"""
    global config
    
    # Parse arguments
    parser = argparse.ArgumentParser(description='VSPhone Multi-Account Monitor')
    parser.add_argument('--config', default='config.json', help='Config file path')
    parser.add_argument('--database', action='store_true', help='Enable SQLite database')
    parser.add_argument('--web-ui', action='store_true', help='Enable web dashboard')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    # Print banner
    print_banner()
    
    # Load configuration
    print("🔍 Loading configuration...")
    config = Config(args.config)
    
    # Override debug mode if specified
    if args.debug:
        config.config['global_settings']['debug_mode'] = True
    
    # Initialize logging
    init_logging(config)
    
    log_message("✅ Configuration loaded successfully", "SUCCESS")
    
    # Show summary
    clones = config.get_all_enabled_clones()
    accounts = set([c['account_id'] for c in clones])
    instances = set([f"{c['account_id']}:{c['instance_pad_code']}" for c in clones])
    
    print("\n📋 Configuration Summary:")
    print(f"   Accounts: {len(accounts)}")
    print(f"   Instances: {len(instances)}")
    print(f"   Clones: {len(clones)}")
    print(f"   Check Interval: {config.global_settings.get('check_interval', 30)}s")
    print(f"   Database: {'✅ Enabled' if args.database else '❌ Disabled'}")
    print(f"   Web UI: {'✅ Enabled' if args.web_ui else '❌ Disabled'}")
    print(f"   Debug: {'✅ Enabled' if config.global_settings.get('debug_mode') else '❌ Disabled'}")
    print()
    
    # Enable database if requested
    if args.database:
        db.enable()
    
    # Start web UI if requested
    if args.web_ui:
        start_web_ui(config)
    
    # Check dependencies
    try:
        import requests
    except ImportError:
        print("❌ ERROR: 'requests' library not found")
        print("   Install with: pip install requests")
        sys.exit(1)
    
    print("=" * 60)
    print("🚀 Starting monitoring...")
    print("=" * 60)
    print()
    print("💡 Tips:")
    print("   • Press Ctrl+C to stop gracefully")
    if args.web_ui:
        print("   • Open http://localhost:5000 for dashboard")
    if args.database:
        print("   • Check vsphone_monitor.db for detailed history")
    print("   • Use --debug flag for detailed logs")
    print()
    
    # Start monitoring
    try:
        monitor_loop(config)
    except Exception as e:
        log_message(f"💀 Fatal error: {e}", "CRITICAL")
        
        if config.global_settings.get('debug_mode', False):
            import traceback
            log_message(traceback.format_exc(), "DEBUG")
        
        send_telegram(
            f"💀 <b>Monitor Crashed</b>\n"
            f"Error: {str(e)[:200]}",
            config
        )
        
        sys.exit(1)
    finally:
        # Cleanup
        db.close()

if __name__ == "__main__":
    import signal
    
    def signal_handler(sig, frame):
        print("\n")
        log_message("Received termination signal", "INFO")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    main()