#!/usr/bin/env python3
"""
Script untuk mendapatkan semua pad_code dari VSPhone account
"""

import requests
import hashlib
import hmac
import json
from datetime import datetime, timezone

# ===== KONFIGURASI - ISI DENGAN DATA ANDA =====
ACCESS_KEY_ID = "WpUO0r4Wpdb1HRvgLaFd7BVcuztJecol"
SECRET_ACCESS_KEY = "l6GHq2ZvPvwnWpq66aFeqQcR"
# ================================================

BASE_URL = "https://api.vsphone.com"

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

def make_api_request(endpoint, body=None):
    """Make authenticated API request"""
    x_date = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    signature = get_signature(body, x_date, SECRET_ACCESS_KEY)
    short_date = x_date[:8]
    
    headers = {
        'content-type': 'application/json;charset=UTF-8',
        'x-date': x_date,
        'x-host': 'api.vsphone.com',
        'authorization': f'HMAC-SHA256 Credential={ACCESS_KEY_ID}/{short_date}/armcloud-paas/request, SignedHeaders=content-type;host;x-content-sha256;x-date, Signature={signature}'
    }
    
    url = f"{BASE_URL}{endpoint}"
    
    try:
        if body:
            response = requests.post(url, headers=headers, json=body, timeout=15)
        else:
            response = requests.get(url, headers=headers, timeout=15)
        
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ API Error: {e}")
        return None

def get_all_instances():
    """Get list of all instances"""
    
    print("🔍 Mengambil daftar semua instances dari VSPhone...")
    print("=" * 60)
    
    # Call API to get instance list
    # Empty body will return all instances
    result = make_api_request("/vsphone/api/padApi/userPadList", {})
    
    if not result or result.get("code") != 200:
        print("-")
        if result:
            print(f"   Error: {result.get('msg', 'Unknown error')}")
        return
    
    instances = result.get("data", [])
    
    if not instances:
        print("⚠️  Tidak ada instances ditemukan")
        return
    
    print(f"✅ Ditemukan {len(instances)} instances\n")
    print("=" * 60)
    print("📋 DAFTAR INSTANCES:")
    print("=" * 60)
    
    for i, instance in enumerate(instances, 1):
        pad_code = instance.get("padCode", "N/A")
        pad_name = instance.get("padName", "Unnamed")
        status = instance.get("status")
        vm_status = "🟢 Online" if instance.get("vmStatus") == 1 else "🔴 Offline"
        location = instance.get("location", "N/A")
        
        print(f"\n{i}. {pad_name}")
        print(f"   pad_code: {pad_code}")
        print(f"   Status: {vm_status}")
        print(f"   Location: {location}")
    
    print("\n" + "=" * 60)
    print("📝 CONFIG.JSON FORMAT:")
    print("=" * 60)
    
    # Generate config format
    print("\n\"instances\": [")
    for i, instance in enumerate(instances):
        pad_code = instance.get("padCode", "N/A")
        pad_name = instance.get("padName", f"Device {i+1}")
        location = instance.get("location", "Unknown")
        
        print("  {")
        print(f"    \"pad_code\": \"{pad_code}\",")
        print(f"    \"name\": \"{pad_name}\",")
        print(f"    \"enabled\": true,")
        print(f"    \"location\": \"{location}\",")
        print("    ")
        print("    \"clones\": [")
        print("      {")
        print(f"        \"name\": \"Roblox Clone {i+1}\",")
        print("        \"package\": \"com.mangcut.rulod\",")
        print("        \"server_url\": \"YOUR_ROBLOX_SERVER_URL\",")
        print("        \"enabled\": true")
        print("      }")
        print("    ]")
        
        if i < len(instances) - 1:
            print("  },")
        else:
            print("  }")
    
    print("]")
    print("\n" + "=" * 60)

def main():
    print("""
╔════════════════════════════════════════════════════╗
║   VSPhone pad_code Getter                          ║
║   Script untuk mendapatkan semua pad_code          ║
╚════════════════════════════════════════════════════╝
    """)
    
    if not ACCESS_KEY_ID or not SECRET_ACCESS_KEY:
        print("❌ ERROR: ACCESS_KEY_ID dan SECRET_ACCESS_KEY belum diisi!")
        print("   Edit script ini dan isi kredensial Anda")
        return
    
    get_all_instances()
    
    print("\n💡 Langkah selanjutnya:")
    print("   1. Copy pad_code untuk setiap device")
    print("   2. Update config.json dengan pad_code yang benar")
    print("   3. Pastikan 'enabled': true untuk semua instances")
    print("   4. Run: python monitor_v5_final.py --debug\n")

if __name__ == "__main__":
    main()