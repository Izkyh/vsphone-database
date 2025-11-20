#!/usr/bin/env python3
"""
Reset Database Script
Fixes database schema issues
"""

import sqlite3
from pathlib import Path
import shutil
from datetime import datetime

DB_FILE = "vsphone_monitor.db"

def backup_database():
    """Backup existing database"""
    if Path(DB_FILE).exists():
        backup_name = f"vsphone_monitor_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy(DB_FILE, backup_name)
        print(f"✅ Backup created: {backup_name}")
        return True
    return False

def reset_database():
    """Reset database with correct schema"""
    
    print("🔧 VSPhone Database Reset Tool")
    print("=" * 60)
    
    # Check if database exists
    if Path(DB_FILE).exists():
        print(f"⚠️  Database found: {DB_FILE}")
        print(f"   Size: {Path(DB_FILE).stat().st_size / 1024:.1f} KB")
        
        choice = input("\n❓ Reset database? (backup will be created) [y/N]: ").strip().lower()
        
        if choice != 'y':
            print("❌ Cancelled")
            return
        
        # Backup
        backup_database()
        
        # Delete old database
        Path(DB_FILE).unlink()
        print(f"✅ Old database deleted")
    
    # Create new database with correct schema
    print(f"\n🔨 Creating new database...")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
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
            error_message TEXT,
            detection_method TEXT
        )
    ''')
    
    # Clone status table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clone_status (
            clone_key TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            instance_pad_code TEXT NOT NULL,
            clone_package TEXT NOT NULL,
            clone_name TEXT NOT NULL,
            instance_name TEXT,
            last_check DATETIME,
            is_healthy BOOLEAN,
            last_issue_type TEXT,
            total_crashes INTEGER DEFAULT 0,
            total_disconnects INTEGER DEFAULT 0,
            total_hangs INTEGER DEFAULT 0,
            last_restart DATETIME,
            detection_confidence REAL DEFAULT 0
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
    
    conn.commit()
    conn.close()
    
    print(f"✅ New database created: {DB_FILE}")
    print(f"\n📊 Schema created:")
    print(f"   ✅ events (with instance_name)")
    print(f"   ✅ clone_status (with instance_name)")
    print(f"   ✅ statistics")
    
    print(f"\n🎉 Database reset complete!")
    print(f"\n💡 Next steps:")
    print(f"   1. Run: python monitor_v5_final.py --database --web-ui")
    print(f"   2. Database will be populated automatically")

def check_schema():
    """Check current database schema"""
    
    if not Path(DB_FILE).exists():
        print(f"❌ Database not found: {DB_FILE}")
        print(f"💡 Run with --reset to create new database")
        return
    
    print(f"🔍 Checking database schema...")
    print(f"=" * 60)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Check tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    print(f"\n📋 Tables:")
    for table in tables:
        print(f"   ✅ {table[0]}")
    
    # Check clone_status columns
    print(f"\n📊 clone_status columns:")
    cursor.execute("PRAGMA table_info(clone_status)")
    columns = cursor.fetchall()
    
    has_instance_name = False
    for col in columns:
        print(f"   • {col[1]} ({col[2]})")
        if col[1] == 'instance_name':
            has_instance_name = True
    
    if has_instance_name:
        print(f"\n✅ Schema is correct (has instance_name)")
    else:
        print(f"\n⚠️  Schema is OLD (missing instance_name)")
        print(f"💡 Run: python reset_database.py --reset")
    
    # Check events columns
    print(f"\n📊 events columns:")
    cursor.execute("PRAGMA table_info(events)")
    columns = cursor.fetchall()
    
    for col in columns:
        print(f"   • {col[1]} ({col[2]})")
    
    # Check row counts
    print(f"\n📈 Row counts:")
    cursor.execute("SELECT COUNT(*) FROM events")
    events_count = cursor.fetchone()[0]
    print(f"   • events: {events_count:,}")
    
    cursor.execute("SELECT COUNT(*) FROM clone_status")
    status_count = cursor.fetchone()[0]
    print(f"   • clone_status: {status_count}")
    
    conn.close()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--reset':
        reset_database()
    elif len(sys.argv) > 1 and sys.argv[1] == '--check':
        check_schema()
    else:
        print("""
╔══════════════════════════════════════════════════════════════╗
║           VSPhone Database Reset Tool                        ║
╚══════════════════════════════════════════════════════════════╝

Usage:
  python reset_database.py --check     Check current schema
  python reset_database.py --reset     Reset database

Options:
  --check   Check database schema (non-destructive)
  --reset   Reset database with correct schema (creates backup)

Examples:
  # Check if database needs reset
  python reset_database.py --check

  # Reset database (backup will be created)
  python reset_database.py --reset

⚠️  Warning: --reset will delete old database (after backup)
""")