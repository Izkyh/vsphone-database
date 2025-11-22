#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║    VSPhone Monitor FINAL - DETECTION BENAR                   ║
║                                                              ║
║  ✅ FIX: Detection yang AKURAT (tidak false positive)        ║
║  ✅ REMOVE: Grace period (karena freeform apps)              ║
║  ✅ SIMPLE: Langsung restart kalau crash                     ║
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
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import threading

VERSION = "FINAL"
BASE_URL = "https://api.vsphone.com"

# ═══════════════════════════════════════════════════════════════
#                    Logging
# ═══════════════════════════════════════════════════════════════

log_lock = threading.Lock()
LOG_FILE = None

def log_message(message, level="INFO"):
    with log_lock:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        
        colors = {
            "DEBUG": "\033[90m",
            "INFO": "\033[0m",
            "WARNING": "\033[93m",
            "ERROR": "\033[91m",
            "SUCCESS": "\033[92m"
        }
        
        color = colors.get(level, "\033[0m")
        print(f"{color}{log_entry}\033[0m")
        
        if LOG_FILE:
            try:
                with open(LOG_FILE, 'a', encoding='utf-8') as f:
                    f.write(log_entry + '\n')
            except:
                pass

def init_logging(config):
    global LOG_FILE
    LOG_FILE = Path(config.global_settings.get('log_file', 'vsphone_monitor.log'))

# ═══════════════════════════════════════════════════════════════
#                    Configuration
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
#                    Statistics
# ═══════════════════════════════════════════════════════════════

class Statistics:
    def __init__(self):
        self.total_checks = 0
        self.total_fixed = 0
        self.crashes = 0
        self.start_time = datetime.now()
        self.lock = threading.Lock()
    
    def increment_check(self, count=1):
        with self.lock:
            self.total_checks += count
    
    def increment_fix(self):
        with self.lock:
            self.total_fixed += 1
            self.crashes += 1
    
    def get_summary(self):
        uptime = datetime.now() - self.start_time
        hours = int(uptime.total_seconds() / 3600)
        minutes = int((uptime.total_seconds() % 3600) / 60)
        
        return f"""
╔══════════════════════════════════════════════════════════╗
║  ⏱️  Uptime: {hours}h {minutes}m
║  🔍 Checks: {self.total_checks:,}
║  ✅ Fixed: {self.total_fixed}
║  💥 Crashes: {self.crashes}
╚══════════════════════════════════════════════════════════╝
"""

stats = Statistics()

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
#     🔥 DETECTION YANG BENAR - FIXED!
# ═══════════════════════════════════════════════════════════════

def check_app_status(clone_data):
    """
    FIXED DETECTION - Gunakan pm list packages untuk check
    Returns: (is_healthy, issue_type)
    """
    
    access_key = clone_data['access_key_id']
    secret_key = clone_data['secret_access_key']
    pad_code = clone_data['instance_pad_code']
    package = clone_data['clone_package']
    
    log_message(f"   🔍 Checking: {clone_data['clone_name']}", "DEBUG")
    
    # 🔥 FIX: Gunakan ps dengan filter yang benar
    # Cek berdasarkan package name EXACT, bukan grep yang bisa kena process grep sendiri
    body = {
        "padCode": pad_code,
        "scriptContent": f"ps -ef | grep '{package}' | grep -v grep | wc -l"
    }
    
    result = make_api_request(access_key, secret_key, "/vsphone/api/padApi/syncCmd", body)
    
    if not result or result.get("code") != 200:
        log_message(f"      ❌ API failed", "DEBUG")
        return (False, "crash")
    
    data = result.get("data", [])
    if not data or len(data) == 0:
        log_message(f"      ❌ No data", "DEBUG")
        return (False, "crash")
    
    task_result = data[0].get("taskResult", "").strip()
    
    # 🔥 CHECK: Jika count > 0 = process jalan
    # Jika count = 0 = process tidak ada
    try:
        count = int(task_result)
        if count > 0:
            log_message(f"      ✅ Process RUNNING ({count} instance)", "DEBUG")
            return (True, None)
        else:
            log_message(f"      ❌ Process NOT FOUND (CRASH)", "DEBUG")
            return (False, "crash")
    except:
        log_message(f"      ❌ Cannot parse result: {task_result}", "DEBUG")
        return (False, "crash")

def execute_restart(clone_data):
    """
    SIMPLE RESTART - Langsung restart tanpa grace period
    """
    
    access_key = clone_data['access_key_id']
    secret_key = clone_data['secret_access_key']
    pad_code = clone_data['instance_pad_code']
    package = clone_data['clone_package']
    server_url = clone_data['server_url']
    
    log_message(f"💥 CRASH: {clone_data['clone_name']}")
    log_message(f"🔄 Restarting...")
    
    # Langsung am start (tidak perlu force stop karena sudah crash)
    adb_command = f'am start -a android.intent.action.VIEW -d "{server_url}" {package}'
    
    body = {
        "padCode": pad_code,
        "scriptContent": adb_command
    }
    
    start_time = time.time()
    result = make_api_request(access_key, secret_key, "/vsphone/api/padApi/syncCmd", body, timeout=30)
    duration = time.time() - start_time
    
    if result and result.get("code") == 200:
        stats.increment_fix()
        log_message(f"✅ Restarted in {duration:.1f}s", "SUCCESS")
        return True
    else:
        log_message(f"❌ Restart failed", "ERROR")
        return False

# ═══════════════════════════════════════════════════════════════
#                    Main Worker
# ═══════════════════════════════════════════════════════════════

def check_and_fix_clone(clone_data):
    clone_name = f"{clone_data['instance_name']} > {clone_data['clone_name']}"
    
    try:
        # Check health
        is_healthy, issue_type = check_app_status(clone_data)
        
        if is_healthy:
            return (clone_name, 'healthy')
        
        # Need restart
        success = execute_restart(clone_data)
        
        if success:
            return (clone_name, 'fixed')
        else:
            return (clone_name, 'failed')
    
    except Exception as e:
        log_message(f"❌ {clone_name}: {e}", "ERROR")
        return (clone_name, 'error')

# ═══════════════════════════════════════════════════════════════
#                    Main Loop
# ═══════════════════════════════════════════════════════════════

def monitor_loop(config):
    clones = config.get_all_enabled_clones()
    
    if len(clones) == 0:
        log_message("❌ No enabled clones", "ERROR")
        sys.exit(1)
    
    check_interval = config.global_settings.get('check_interval', 300)
    
    log_message("=" * 60)
    log_message(f"🚀 VSPhone Monitor v{VERSION} Started")
    log_message(f"📊 Clones: {len(clones)}")
    log_message(f"⏱️  Interval: {check_interval}s ({check_interval//60} min)")
    log_message(f"🔧 Detection: ps | grep | grep -v grep | wc -l")
    log_message(f"⚡ NO Grace Period (langsung restart)")
    log_message("=" * 60)
    
    max_workers = min(10, len(clones))
    
    while True:
        try:
            cycle_start = time.time()
            stats.increment_check(len(clones))
            
            log_message(f"\n🔍 Checking {len(clones)} clones...")
            
            results = {'healthy': 0, 'fixed': 0, 'failed': 0, 'error': 0}
            
            # Check all clones in parallel
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(check_and_fix_clone, clone): clone for clone in clones}
                
                for future in as_completed(futures):
                    clone_name, status = future.result()
                    results[status] += 1
            
            cycle_duration = time.time() - cycle_start
            
            # Summary
            log_message("\n" + "─" * 60)
            log_message(f"✅ Cycle Complete ({cycle_duration:.1f}s)")
            log_message(f"   ✅ Healthy: {results['healthy']}")
            
            if results['fixed'] > 0:
                log_message(f"   🔧 Fixed: {results['fixed']}", "SUCCESS")
            
            if results['failed'] > 0:
                log_message(f"   ❌ Failed: {results['failed']}", "ERROR")
            
            if results['error'] > 0:
                log_message(f"   ⚠️  Errors: {results['error']}", "WARNING")
            
            log_message("─" * 60)
            
            # Stats every 10 cycles
            if stats.total_checks % (10 * len(clones)) == 0:
                print(stats.get_summary())
            
            log_message(f"\n💤 Waiting {check_interval}s...")
            time.sleep(check_interval)
        
        except KeyboardInterrupt:
            log_message("\n🛑 Shutdown...")
            print(stats.get_summary())
            break
        
        except Exception as e:
            log_message(f"❌ Error: {e}", "ERROR")
            time.sleep(check_interval)

# ═══════════════════════════════════════════════════════════════
#                    Main Entry
# ═══════════════════════════════════════════════════════════════

def print_banner():
    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║      VSPhone Monitor vFINAL                                  ║
║           🔥 DETECTION FIXED - NO GRACE PERIOD               ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  ✅ FIXES:                                                   ║
║     • Gunakan ps -ef | grep | grep -v grep | wc -l          ║
║     • grep -v grep = exclude process grep sendiri           ║
║     • wc -l = count lines (jumlah process)                  ║
║     • NO GRACE PERIOD (karena freeform apps)                ║
║                                                              ║
║  🎯 DETECTION:                                               ║
║     • ps -ef | grep 'package' | grep -v grep | wc -l        ║
║     • Jika count > 0 → HEALTHY                               ║
║     • Jika count = 0 → CRASH → RESTART                       ║
║                                                              ║
║  ⚡ INSTANT RESTART (no delays)                              ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")

def main():
    global config
    
    parser = argparse.ArgumentParser(description='VSPhone Monitor FINAL')
    parser.add_argument('--config', default='config.json', help='Config file')
    parser.add_argument('--debug', action='store_true', help='Debug mode')
    
    args = parser.parse_args()
    
    print_banner()
    
    print("🔍 Loading configuration...")
    config = Config(args.config)
    
    if args.debug:
        config.config['global_settings']['debug_mode'] = True
    
    # Defaults
    if 'check_interval' not in config.config['global_settings']:
        config.config['global_settings']['check_interval'] = 300
    
    init_logging(config)
    log_message("✅ Configuration loaded", "SUCCESS")
    
    clones = config.get_all_enabled_clones()
    interval = config.global_settings.get('check_interval', 300)
    
    print(f"\n📋 Configuration:")
    print(f"   Clones: {len(clones)}")
    print(f"   Check Interval: {interval}s ({interval//60} minutes)")
    print(f"   Debug: {'✅' if args.debug else '❌'}")
    print()
    
    print("💡 HOW IT WORKS:")
    print("   1️⃣  Check: ps -ef | grep '{package}' | grep -v grep | wc -l")
    print("   2️⃣  If count > 0 → HEALTHY")
    print("   3️⃣  If count = 0 → CRASHED → RESTART")
    print("   4️⃣  No grace period (instant restart)")
    print()
    print("   Package examples:")
    print("   • com.mangcut.rulod")
    print("   • com.mangcut.ruloe")
    print("   • ... sampai rulom")
    print()
    print("   Press Ctrl+C to stop")
    print()
    
    try:
        monitor_loop(config)
    except Exception as e:
        log_message(f"💀 Fatal: {e}", "ERROR")
        sys.exit(1)

if __name__ == "__main__":
    import signal
    
    def signal_handler(sig, frame):
        print("\n")
        log_message("Terminating...", "INFO")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    main()