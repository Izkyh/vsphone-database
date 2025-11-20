#!/usr/bin/env python3
"""
VSPhone Monitor - Web Dashboard
Flask-based real-time monitoring dashboard
"""

from flask import Flask, render_template_string, jsonify, request
from datetime import datetime, timedelta
import json

app = Flask(__name__)

# Global references
config_ref = None
db_ref = None
stats_ref = None

def init_app(config, db, stats):
    """Initialize app with references"""
    global config_ref, db_ref, stats_ref
    config_ref = config
    db_ref = db
    stats_ref = stats

# ═══════════════════════════════════════════════════════════════
#                    HTML Template
# ═══════════════════════════════════════════════════════════════

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VSPhone Monitor Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        .header {
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 30px;
            text-align: center;
        }
        
        .header h1 {
            color: #667eea;
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .header p {
            color: #666;
            font-size: 1.1em;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        
        .stat-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.15);
        }
        
        .stat-icon {
            font-size: 3em;
            margin-bottom: 10px;
        }
        
        .stat-value {
            font-size: 2.5em;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 5px;
        }
        
        .stat-label {
            color: #666;
            font-size: 1.1em;
        }
        
        .clones-section {
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 30px;
        }
        
        .clones-section h2 {
            color: #667eea;
            margin-bottom: 20px;
            font-size: 1.8em;
        }
        
        .filters {
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        
        .filter-btn {
            padding: 10px 20px;
            border: 2px solid #667eea;
            background: white;
            color: #667eea;
            border-radius: 25px;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 1em;
        }
        
        .filter-btn:hover {
            background: #667eea;
            color: white;
        }
        
        .filter-btn.active {
            background: #667eea;
            color: white;
        }
        
        .clones-table {
            width: 100%;
            border-collapse: collapse;
        }
        
        .clones-table th {
            background: #667eea;
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
        }
        
        .clones-table td {
            padding: 15px;
            border-bottom: 1px solid #eee;
        }
        
        .clones-table tr:hover {
            background: #f8f9ff;
        }
        
        .status-badge {
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: 600;
            display: inline-block;
        }
        
        .status-healthy {
            background: #d4edda;
            color: #155724;
        }
        
        .status-issue {
            background: #fff3cd;
            color: #856404;
        }
        
        .status-error {
            background: #f8d7da;
            color: #721c24;
        }
        
        .last-update {
            text-align: center;
            color: white;
            margin-top: 20px;
            font-size: 1.1em;
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            color: #666;
        }
        
        .loading::after {
            content: '...';
            animation: dots 1.5s steps(4, end) infinite;
        }
        
        @keyframes dots {
            0%, 20% { content: '.'; }
            40% { content: '..'; }
            60%, 100% { content: '...'; }
        }
        
        .auto-refresh {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            padding: 15px;
            background: rgba(255,255,255,0.2);
            border-radius: 10px;
            margin-top: 20px;
        }
        
        .auto-refresh input[type="checkbox"] {
            width: 20px;
            height: 20px;
            cursor: pointer;
        }
        
        .auto-refresh label {
            color: white;
            font-size: 1.1em;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 VSPhone Monitor Dashboard</h1>
            <p>Real-time monitoring for multi-account Roblox clones</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-icon">📊</div>
                <div class="stat-value" id="total-clones">-</div>
                <div class="stat-label">Total Clones</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-icon">✅</div>
                <div class="stat-value" id="healthy-clones">-</div>
                <div class="stat-label">Healthy</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-icon">🔧</div>
                <div class="stat-value" id="total-fixes">-</div>
                <div class="stat-label">Total Fixes</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-icon">⚡</div>
                <div class="stat-value" id="success-rate">-</div>
                <div class="stat-label">Success Rate</div>
            </div>
        </div>
        
        <div class="clones-section">
            <h2>Clone Status</h2>
            
            <div class="filters">
                <button class="filter-btn active" data-filter="all">All Clones</button>
                <button class="filter-btn" data-filter="healthy">Healthy Only</button>
                <button class="filter-btn" data-filter="issues">With Issues</button>
                <button class="filter-btn" data-filter="account">By Account</button>
            </div>
            
            <div id="clones-content">
                <div class="loading">Loading clone data</div>
            </div>
        </div>
        
        <div class="auto-refresh">
            <input type="checkbox" id="auto-refresh" checked>
            <label for="auto-refresh">Auto-refresh every 10 seconds</label>
        </div>
        
        <div class="last-update" id="last-update">
            Last updated: -
        </div>
    </div>
    
    <script>
        let currentFilter = 'all';
        let autoRefreshInterval = null;
        
        // Filter buttons
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                currentFilter = this.dataset.filter;
                loadData();
            });
        });
        
        // Auto-refresh toggle
        document.getElementById('auto-refresh').addEventListener('change', function() {
            if (this.checked) {
                startAutoRefresh();
            } else {
                stopAutoRefresh();
            }
        });
        
        function startAutoRefresh() {
            autoRefreshInterval = setInterval(loadData, 10000);
        }
        
        function stopAutoRefresh() {
            if (autoRefreshInterval) {
                clearInterval(autoRefreshInterval);
                autoRefreshInterval = null;
            }
        }
        
        async function loadData() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                
                // Update stats
                document.getElementById('total-clones').textContent = data.total_clones;
                document.getElementById('healthy-clones').textContent = data.healthy_clones;
                document.getElementById('total-fixes').textContent = data.total_fixes;
                document.getElementById('success-rate').textContent = data.success_rate + '%';
                
                // Update clones table
                renderClones(data.clones);
                
                // Update timestamp
                document.getElementById('last-update').textContent = 
                    'Last updated: ' + new Date().toLocaleTimeString();
                
            } catch (error) {
                console.error('Failed to load data:', error);
                document.getElementById('clones-content').innerHTML = 
                    '<div class="loading">Failed to load data. Retrying...</div>';
            }
        }
        
        function renderClones(clones) {
            // Filter clones
            let filtered = clones;
            
            if (currentFilter === 'healthy') {
                filtered = clones.filter(c => c.is_healthy);
            } else if (currentFilter === 'issues') {
                filtered = clones.filter(c => !c.is_healthy || c.total_issues > 0);
            }
            
            // Sort by issues (most problematic first)
            filtered.sort((a, b) => b.total_issues - a.total_issues);
            
            let html = '<table class="clones-table">';
            html += '<thead><tr>';
            html += '<th>Account</th>';
            html += '<th>Instance</th>';
            html += '<th>Clone</th>';
            html += '<th>Status</th>';
            html += '<th>Total Issues</th>';
            html += '<th>Crashes</th>';
            html += '<th>Disconnects</th>';
            html += '<th>Hangs</th>';
            html += '<th>Last Check</th>';
            html += '</tr></thead><tbody>';
            
            if (filtered.length === 0) {
                html += '<tr><td colspan="9" style="text-align:center; padding:40px; color:#999;">No clones found</td></tr>';
            } else {
                filtered.forEach(clone => {
                    let statusClass = clone.is_healthy ? 'status-healthy' : 
                                    clone.total_issues > 5 ? 'status-error' : 'status-issue';
                    let statusText = clone.is_healthy ? '✅ Healthy' : 
                                    '⚠️ ' + (clone.last_issue_type || 'Issue');
                    
                    html += '<tr>';
                    html += `<td>${clone.account_name || clone.account_id}</td>`;
                    html += `<td>${clone.instance_name}</td>`;
                    html += `<td>${clone.clone_name}</td>`;
                    html += `<td><span class="status-badge ${statusClass}">${statusText}</span></td>`;
                    html += `<td>${clone.total_issues}</td>`;
                    html += `<td>${clone.total_crashes}</td>`;
                    html += `<td>${clone.total_disconnects}</td>`;
                    html += `<td>${clone.total_hangs}</td>`;
                    html += `<td>${clone.last_check ? new Date(clone.last_check).toLocaleTimeString() : '-'}</td>`;
                    html += '</tr>';
                });
            }
            
            html += '</tbody></table>';
            
            document.getElementById('clones-content').innerHTML = html;
        }
        
        // Initial load
        loadData();
        
        // Start auto-refresh
        if (document.getElementById('auto-refresh').checked) {
            startAutoRefresh();
        }
    </script>
</body>
</html>
"""

# ═══════════════════════════════════════════════════════════════
#                    API Endpoints
# ═══════════════════════════════════════════════════════════════

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/status')
def api_status():
    """Get current status of all clones"""
    
    try:
        # Get clone list from config
        clones = config_ref.get_all_enabled_clones()
        
        # Get database stats if available
        clone_statuses = []
        
        if db_ref and db_ref.enabled:
            try:
                cursor = db_ref.conn.cursor()
                
                # Check if table exists and get columns
                cursor.execute("PRAGMA table_info(clone_status)")
                columns = [row[1] for row in cursor.fetchall()]
                
                # Build SELECT based on available columns
                if 'instance_name' in columns:
                    # New schema
                    cursor.execute('''
                        SELECT clone_key, clone_name, account_id, instance_pad_code, instance_name,
                               last_check, is_healthy, last_issue_type,
                               total_crashes, total_disconnects, total_hangs
                        FROM clone_status
                    ''')
                else:
                    # Old schema (no instance_name)
                    cursor.execute('''
                        SELECT clone_key, clone_name, account_id, instance_pad_code,
                               last_check, is_healthy, last_issue_type,
                               total_crashes, total_disconnects, total_hangs
                        FROM clone_status
                    ''')
                
                rows = cursor.fetchall()
                
                for row in rows:
                    if 'instance_name' in columns:
                        # New schema (with instance_name)
                        clone_statuses.append({
                            'clone_key': row[0],
                            'clone_name': row[1],
                            'account_id': row[2],
                            'account_name': row[2],
                            'instance_pad_code': row[3],
                            'instance_name': row[4],
                            'last_check': row[5],
                            'is_healthy': bool(row[6]) if row[6] is not None else True,
                            'last_issue_type': row[7],
                            'total_crashes': row[8] or 0,
                            'total_disconnects': row[9] or 0,
                            'total_hangs': row[10] or 0,
                            'total_issues': (row[8] or 0) + (row[9] or 0) + (row[10] or 0)
                        })
                    else:
                        # Old schema (no instance_name)
                        clone_statuses.append({
                            'clone_key': row[0],
                            'clone_name': row[1],
                            'account_id': row[2],
                            'account_name': row[2],
                            'instance_pad_code': row[3],
                            'instance_name': 'Unknown',
                            'last_check': row[4],
                            'is_healthy': bool(row[5]) if row[5] is not None else True,
                            'last_issue_type': row[6],
                            'total_crashes': row[7] or 0,
                            'total_disconnects': row[8] or 0,
                            'total_hangs': row[9] or 0,
                            'total_issues': (row[7] or 0) + (row[8] or 0) + (row[9] or 0)
                        })
                        
            except Exception as db_error:
                print(f"Database error: {db_error}")
                # Fallback to config
                for clone in clones:
                    clone_statuses.append({
                        'clone_name': clone['clone_name'],
                        'account_id': clone['account_id'],
                        'account_name': clone.get('account_name', clone['account_id']),
                        'instance_pad_code': clone['instance_pad_code'],
                        'instance_name': clone['instance_name'],
                        'last_check': 'Never',
                        'is_healthy': True,
                        'last_issue_type': None,
                        'total_crashes': 0,
                        'total_disconnects': 0,
                        'total_hangs': 0,
                        'total_issues': 0
                    })
        else:
            # No database - show basic info from config
            for clone in clones:
                clone_statuses.append({
                    'clone_name': clone['clone_name'],
                    'account_id': clone['account_id'],
                    'account_name': clone.get('account_name', clone['account_id']),
                    'instance_pad_code': clone['instance_pad_code'],
                    'instance_name': clone['instance_name'],
                    'last_check': 'Never',
                    'is_healthy': True,
                    'last_issue_type': None,
                    'total_crashes': 0,
                    'total_disconnects': 0,
                    'total_hangs': 0,
                    'total_issues': 0
                })
        
        # Calculate summary
        total_clones = len(clone_statuses)
        healthy_clones = sum(1 for c in clone_statuses if c.get('is_healthy', True))
        
        # Get stats from stats object
        total_fixes = stats_ref.total_fixed if stats_ref else 0
        total_failed = stats_ref.total_failed if stats_ref else 0
        success_rate = round((total_fixes / max(total_fixes + total_failed, 1)) * 100, 1) if (total_fixes + total_failed) > 0 else 0
        
        return jsonify({
            'total_clones': total_clones,
            'healthy_clones': healthy_clones,
            'total_fixes': total_fixes,
            'success_rate': success_rate,
            'clones': clone_statuses
        })
    
    except Exception as e:
        print(f"API Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'total_clones': 0,
            'healthy_clones': 0,
            'total_fixes': 0,
            'success_rate': 0,
            'clones': []
        }), 200  # Return 200 with empty data instead of 500

@app.route('/api/stats')
def api_stats():
    """Get overall statistics"""
    
    try:
        stats_data = {
            'total_checks': stats_ref.total_checks if stats_ref else 0,
            'total_fixed': stats_ref.total_fixed if stats_ref else 0,
            'total_failed': stats_ref.total_failed if stats_ref else 0,
            'crashes': stats_ref.crashes if stats_ref else 0,
            'disconnects': stats_ref.disconnects if stats_ref else 0,
            'hangs': stats_ref.hangs if stats_ref else 0,
        }
        
        # Add database stats if available
        if db_ref.enabled:
            db_stats = db_ref.get_statistics(24)
            stats_data['last_24h'] = db_stats
        
        return jsonify(stats_data)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("⚠️  Please run this through monitor_v5.py with --web-ui flag")
    print("   Example: python monitor_v5.py --web-ui")