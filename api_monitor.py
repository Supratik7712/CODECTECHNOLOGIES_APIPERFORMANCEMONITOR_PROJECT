#API Performance Monitor
import time
import requests
import sqlite3
import threading
import logging
import signal
import sys
from datetime import datetime
from flask import Flask, render_template_string, g


DATABASE = "metrics.db"
CHECK_INTERVAL = 10  # seconds
API_ENDPOINTS = [
    {"url": "https://jsonplaceholder.typicode.com/posts", "method": "GET"},
    {"url": "https://jsonplaceholder.typicode.com/comments", "method": "GET"},
    {"url": "https://jsonplaceholder.typicode.com/users", "method": "GET"}
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


app = Flask(__name__)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            endpoint TEXT,
            method TEXT,
            response_time REAL,
            status_code INTEGER,
            success INTEGER,
            error_message TEXT
        )
    ''')
    conn.commit()
    conn.close()


def log_metric(endpoint, method, response_time, status_code, success, error_message=None):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO metrics (timestamp, endpoint, method, response_time, status_code, success, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (datetime.utcnow().isoformat(), endpoint, method, response_time, status_code, success, error_message))
    conn.commit()
    conn.close()

def monitor_api():
    while True:
        for api in API_ENDPOINTS:
            url = api["url"]
            method = api.get("method", "GET").upper()
            try:
                start = time.time()
                response = requests.request(method, url, timeout=5)
                elapsed = time.time() - start
                log_metric(url, method, elapsed, response.status_code, 1)
                logging.info(f"Checked {url} - {response.status_code} in {elapsed:.2f}s")
            except Exception as e:
                elapsed = time.time() - start
                log_metric(url, method, elapsed, -1, 0, str(e))
                logging.error(f"Error checking {url}: {e}")
        time.sleep(CHECK_INTERVAL)


@app.route("/")
def dashboard():
    db = get_db()
    metrics = db.execute('SELECT * FROM metrics ORDER BY id DESC LIMIT 50').fetchall()
    summary = db.execute('''
        SELECT endpoint,
               COUNT(*) as total,
               SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as successes,
               SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as failures,
               AVG(response_time) as avg_time
        FROM metrics
        GROUP BY endpoint
    ''').fetchall()
    return render_template_string(DASHBOARD_TEMPLATE, metrics=metrics, summary=summary)


DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>API Performance Monitor</title>
    <style>
        body { font-family: Arial, sans-serif; background: #f5f7fa; margin: 20px; }
        h1 { text-align: center; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; background: #fff; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        th, td { padding: 10px; border: 1px solid #ddd; text-align: center; }
        th { background: #4CAF50; color: white; }
        tr:nth-child(even) { background: #f2f2f2; }
        .success { color: green; font-weight: bold; }
        .error { color: red; font-weight: bold; }
        .card { padding: 15px; margin: 20px auto; background: #fff; width: 80%; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
    </style>
</head>
<body>
    <h1>🚀 API Performance Monitor</h1>

    <div class="card">
        <h2>📊 API Summary</h2>
        <table>
            <tr>
                <th>Endpoint</th>
                <th>Total</th>
                <th>Successes</th>
                <th>Failures</th>
                <th>Avg Response Time (s)</th>
                <th>Status</th>
            </tr>
            {% for row in summary %}
            {% set error_rate = (row['failures'] / row['total'] * 100) if row['total'] > 0 else 0 %}
            <tr>
                <td>{{ row['endpoint'] }}</td>
                <td>{{ row['total'] }}</td>
                <td class="success">{{ row['successes'] }}</td>
                <td class="error">{{ row['failures'] }}</td>
                <td>{{ "%.3f"|format(row['avg_time'] or 0) }}</td>
                <td>
                    {% if error_rate > 20 %}
                        <span class="error">⚠️ Unstable</span>
                    {% else %}
                        <span class="success">✅ Healthy</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <div class="card">
        <h2>📋 Recent Checks</h2>
        <table>
            <tr>
                <th>Time</th>
                <th>Endpoint</th>
                <th>Method</th>
                <th>Status</th>
                <th>Response Time (s)</th>
                <th>Error</th>
            </tr>
            {% for m in metrics %}
            <tr>
                <td>{{ m['timestamp'].split('T')[1].split('.')[0] }}</td>
                <td>{{ m['endpoint'] }}</td>
                <td>{{ m['method'] }}</td>
                <td>
                    {% if m['success'] == 1 %}
                        <span class="success">{{ m['status_code'] }}</span>
                    {% else %}
                        <span class="error">Failed</span>
                    {% endif %}
                </td>
                <td>{{ "%.3f"|format(m['response_time']) }}</td>
                <td>{{ m['error_message'] or "-" }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>
</body>
</html>
'''


def main():
    init_db()
    monitor_thread = threading.Thread(target=monitor_api, daemon=True)
    monitor_thread.start()

    def signal_handler(sig, frame):
        logging.info("Shutting down monitor...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()
