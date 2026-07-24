import csv
import os
import smtplib
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import requests
from croniter import croniter

PROM = os.getenv('PROMETHEUS_URL', 'http://prometheus:9090')
REPORTS = Path('/reports')
CRON = os.getenv('REPORT_CRON', '5 8 1 * *')


def query(q):
    r = requests.get(f'{PROM}/api/v1/query', params={'query': q}, timeout=30)
    r.raise_for_status()
    return r.json()['data']['result']


def generate_report():
    REPORTS.mkdir(parents=True, exist_ok=True)
    month = datetime.now().strftime('%Y-%m')
    path = REPORTS / f'sla-{month}.csv'
    rows = query('host:availability_30d:ratio * 100')
    with path.open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['month', 'product', 'application', 'service', 'environment', 'location', 'team', 'host', 'availability_percent', 'downtime_seconds'])
        for item in rows:
            m = item['metric']
            availability = float(item['value'][1])
            downtime = (100 - availability) / 100 * 30 * 24 * 3600
            writer.writerow([month, m.get('product', ''), m.get('application', ''), m.get('service', ''), m.get('environment', ''), m.get('location', ''), m.get('team', ''), m.get('host', ''), round(availability, 5), int(downtime)])
    return path


def send_email(path):
    msg = EmailMessage()
    msg['Subject'] = f'Monthly SLA Report {datetime.now().strftime("%Y-%m")}'
    msg['From'] = os.getenv('SMTP_FROM')
    msg['To'] = os.getenv('SMTP_TO')
    msg.set_content('Attached monthly SLA report generated from Prometheus availability recording rules.')
    msg.add_attachment(path.read_bytes(), maintype='text', subtype='csv', filename=path.name)
    host, port = os.getenv('SMTP_SMARTHOST').rsplit(':', 1)
    with smtplib.SMTP(host, int(port), timeout=30) as smtp:
        smtp.starttls()
        smtp.login(os.getenv('SMTP_AUTH_USERNAME'), os.getenv('SMTP_AUTH_PASSWORD'))
        smtp.send_message(msg)


def main():
    base = datetime.now(timezone.utc)
    itr = croniter(CRON, base)
    while True:
        next_run = itr.get_next(datetime)
        sleep = max(1, (next_run - datetime.now(timezone.utc)).total_seconds())
        time.sleep(sleep)
        path = generate_report()
        send_email(path)


if __name__ == '__main__':
    main()
