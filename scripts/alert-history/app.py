import html
import json
import os
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DB_PATH = Path(os.getenv('DB_PATH', '/data/alert-history.db'))
LISTEN_ADDR = os.getenv('LISTEN_ADDR', '0.0.0.0')
LISTEN_PORT = int(os.getenv('LISTEN_PORT', '8080'))


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None


def duration_seconds(starts_at, resolved_at):
    start = parse_time(starts_at)
    end = parse_time(resolved_at)
    if not start or not end:
        return None
    return max(0, int((end - start).total_seconds()))


def human_duration(seconds):
    if seconds is None:
        return ''
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, sec = divmod(rem, 60)
    if days:
        return f'{days}d {hours}h {minutes}m'
    if hours:
        return f'{hours}h {minutes}m {sec}s'
    if minutes:
        return f'{minutes}m {sec}s'
    return f'{sec}s'


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            create table if not exists alerts (
                id integer primary key autoincrement,
                fingerprint text unique not null,
                status text not null,
                alertname text,
                project text,
                host text,
                service text,
                severity text,
                starts_at text,
                resolved_at text,
                duration_seconds integer,
                summary text,
                description text,
                generator_url text,
                created_at text not null,
                updated_at text not null
            )
        ''')
        conn.execute('create index if not exists idx_alerts_host on alerts(host)')
        conn.execute('create index if not exists idx_alerts_project on alerts(project)')
        conn.execute('create index if not exists idx_alerts_status on alerts(status)')
        conn.execute('create index if not exists idx_alerts_starts_at on alerts(starts_at)')


def upsert_alert(alert):
    labels = alert.get('labels') or {}
    annotations = alert.get('annotations') or {}
    fingerprint = alert.get('fingerprint') or '|'.join(f'{k}={labels[k]}' for k in sorted(labels))
    status = alert.get('status') or 'unknown'
    starts_at = alert.get('startsAt') or alert.get('starts_at')
    ends_at = alert.get('endsAt') or alert.get('ends_at')
    resolved_at = ends_at if status == 'resolved' and ends_at and not ends_at.startswith('0001-') else None
    dur = duration_seconds(starts_at, resolved_at)
    values = {
        'fingerprint': fingerprint,
        'status': status,
        'alertname': labels.get('alertname', ''),
        'project': labels.get('project', ''),
        'host': labels.get('host', ''),
        'service': labels.get('service', ''),
        'severity': labels.get('severity', ''),
        'starts_at': starts_at or '',
        'resolved_at': resolved_at or '',
        'duration_seconds': dur,
        'summary': annotations.get('summary', ''),
        'description': annotations.get('description', ''),
        'generator_url': alert.get('generatorURL', ''),
        'created_at': now_iso(),
        'updated_at': now_iso(),
    }
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            insert into alerts (
                fingerprint, status, alertname, project, host, service, severity,
                starts_at, resolved_at, duration_seconds, summary, description,
                generator_url, created_at, updated_at
            ) values (
                :fingerprint, :status, :alertname, :project, :host, :service, :severity,
                :starts_at, :resolved_at, :duration_seconds, :summary, :description,
                :generator_url, :created_at, :updated_at
            )
            on conflict(fingerprint) do update set
                status=excluded.status,
                alertname=excluded.alertname,
                project=excluded.project,
                host=excluded.host,
                service=excluded.service,
                severity=excluded.severity,
                starts_at=excluded.starts_at,
                resolved_at=case when excluded.resolved_at != '' then excluded.resolved_at else alerts.resolved_at end,
                duration_seconds=case when excluded.duration_seconds is not null then excluded.duration_seconds else alerts.duration_seconds end,
                summary=excluded.summary,
                description=excluded.description,
                generator_url=excluded.generator_url,
                updated_at=excluded.updated_at
        ''', values)


def first_param(params, name, default=''):
    return (params.get(name) or [default])[0].strip()


def fetch_alerts(params):
    try:
        limit = int(first_param(params, 'limit', '200'))
    except ValueError:
        limit = 200
    limit = min(max(limit, 1), 1000)
    host = first_param(params, 'host')
    project = first_param(params, 'project')
    status = first_param(params, 'status')
    where = []
    args = []
    if host:
        where.append('host like ?')
        args.append(f'%{host}%')
    if project:
        where.append('project like ?')
        args.append(f'%{project}%')
    if status:
        where.append('status = ?')
        args.append(status)
    sql = 'select * from alerts'
    if where:
        sql += ' where ' + ' and '.join(where)
    sql += ' order by starts_at desc, updated_at desc limit ?'
    args.append(limit)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(sql, args).fetchall()]


def selected(current, value):
    return ' selected' if current == value else ''


def render_history(params):
    rows = fetch_alerts(params)
    trs = []
    for row in rows:
        status_class = 'resolved' if row['status'] == 'resolved' else 'firing'
        duration = human_duration(row['duration_seconds']) if row['duration_seconds'] is not None else ''
        trs.append(f'''
          <tr>
            <td><span class="badge {status_class}">{html.escape(row['status'])}</span></td>
            <td>{html.escape(row['project'] or '-')}</td>
            <td>{html.escape(row['host'] or '-')}</td>
            <td>{html.escape(row['alertname'] or '-')}</td>
            <td>{html.escape(row['service'] or '-')}</td>
            <td>{html.escape(row['severity'] or '-')}</td>
            <td>{html.escape(row['starts_at'] or '-')}</td>
            <td>{html.escape(row['resolved_at'] or '-')}</td>
            <td>{html.escape(duration or '-')}</td>
            <td>{html.escape(row['summary'] or '-')}</td>
          </tr>
        ''')
    body = '\n'.join(trs) or '<tr><td colspan="10" class="empty">No alert history yet</td></tr>'
    return f'''<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Alert History</title>
  <style>
    body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; background: #0b0f19; color: #e5e7eb; }}
    h1 {{ margin: 0 0 8px; }}
    p {{ color: #9ca3af; margin: 0 0 20px; }}
    form {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }}
    input, select, button {{ background: #111827; color: #e5e7eb; border: 1px solid #374151; border-radius: 6px; padding: 8px 10px; }}
    button {{ cursor: pointer; }}
    table {{ width: 100%; border-collapse: collapse; background: #111827; border-radius: 8px; overflow: hidden; }}
    th, td {{ border-bottom: 1px solid #1f2937; padding: 10px; text-align: left; font-size: 13px; vertical-align: top; }}
    th {{ background: #1f2937; color: #f9fafb; position: sticky; top: 0; }}
    tr:hover {{ background: #172033; }}
    .badge {{ border-radius: 999px; padding: 3px 8px; font-weight: 700; font-size: 12px; }}
    .firing {{ background: #7f1d1d; color: #fecaca; }}
    .resolved {{ background: #064e3b; color: #a7f3d0; }}
    .empty {{ text-align: center; color: #9ca3af; }}
    a {{ color: #93c5fd; }}
  </style>
</head>
<body>
  <h1>Alert History</h1>
  <p>Downtime and alert event history from Alertmanager webhook.</p>
  <form method="get" action="/history/">
    <input name="project" placeholder="project" value="{html.escape(first_param(params, 'project'))}">
    <input name="host" placeholder="host" value="{html.escape(first_param(params, 'host'))}">
    <select name="status">
      <option value=""{selected(first_param(params, 'status'), '')}>all status</option>
      <option value="firing"{selected(first_param(params, 'status'), 'firing')}>firing</option>
      <option value="resolved"{selected(first_param(params, 'status'), 'resolved')}>resolved</option>
    </select>
    <input name="limit" placeholder="limit" value="{html.escape(first_param(params, 'limit', '200'))}">
    <button type="submit">Filter</button>
    <a href="/history/">Reset</a>
  </form>
  <table>
    <thead>
      <tr>
        <th>Status</th><th>Project</th><th>Host</th><th>Alert</th><th>Service</th><th>Severity</th><th>Started</th><th>Resolved</th><th>Duration</th><th>Summary</th>
      </tr>
    </thead>
    <tbody>{body}</tbody>
  </table>
</body>
</html>'''


class Handler(BaseHTTPRequestHandler):
    def send(self, code, content, content_type='text/plain'):
        data = content.encode('utf-8') if isinstance(content, str) else content
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ('/', '/history', '/history/'):
            self.send(200, render_history(parse_qs(parsed.query)), 'text/html; charset=utf-8')
        elif parsed.path == '/health':
            self.send(200, 'ok\n')
        elif parsed.path in ('/api/alerts', '/history/api/alerts'):
            self.send(200, json.dumps(fetch_alerts(parse_qs(parsed.query))), 'application/json')
        else:
            self.send(404, 'not found\n')

    def do_HEAD(self):
        parsed = urlparse(self.path)
        if parsed.path in ('/', '/history', '/history/', '/health', '/api/alerts', '/history/api/alerts'):
            self.send_response(200)
        else:
            self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != '/webhook':
            self.send(404, 'not found\n')
            return
        length = int(self.headers.get('Content-Length', '0'))
        try:
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
            for alert in payload.get('alerts', []):
                upsert_alert(alert)
            self.send(200, 'ok\n')
        except Exception as exc:
            self.send(500, f'error: {exc}\n')

    def log_message(self, fmt, *args):
        return


def main():
    init_db()
    server = ThreadingHTTPServer((LISTEN_ADDR, LISTEN_PORT), Handler)
    server.serve_forever()


if __name__ == '__main__':
    main()
