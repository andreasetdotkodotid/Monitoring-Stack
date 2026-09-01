# Tutorial Install Monitoring Stack Menggunakan Docker Compose

Dokumen ini menjelaskan cara install dan menjalankan Monitoring Stack menggunakan Docker Compose.

Jika ingin install tanpa Docker, baca:

```text
docs/MANUAL_INSTALL_TUTORIAL.md
```

Jika ingin memahami konfigurasi Prometheus, Blackbox, recording rules, dan alert rules, baca:

```text
docs/CONFIGURATION_GUIDE.md
```

## 1. Komponen

Stack Docker ini berisi:

- Prometheus
- Grafana
- Alertmanager
- Karma
- Blackbox Exporter
- Nginx reverse proxy
- Alert History berbasis SQLite
- SLA report generator
- File service discovery generator

Server target hanya perlu menjalankan Node Exporter.

## 2. Struktur Penting

```text
docker-compose.yml
targets.yml
.env
prometheus/
alertmanager/
grafana/
blackbox/
karma/
scripts/
config/
data/
nginx/
```

Folder `data/` berisi data persistent dan tidak boleh dihapus sembarangan.

## 3. Persiapan Server

Install Docker dan Compose plugin:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin git
sudo systemctl enable --now docker
```

Clone repository:

```bash
git clone git@github.com:andreasetdotkodotid/Monitoring-Stack.git
cd Monitoring-Stack
```

## 4. Siapkan Environment

```bash
cp .env.example .env
nano .env
```

Isi yang wajib disesuaikan:

```env
GRAFANA_DOMAIN=monitoring.example.com
GRAFANA_ROOT_URL=https://monitoring.example.com/grafana/
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=change-me
GRAFANA_SECRET_KEY=change-me-long-random

GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxx
GOOGLE_ALLOWED_DOMAINS=example.com

SMTP_FROM=monitoring@example.com
SMTP_SMARTHOST=smtp.example.com:587
SMTP_AUTH_USERNAME=monitoring@example.com
SMTP_AUTH_PASSWORD=change-me
SMTP_TO=sre@example.com
SMTP_REQUIRE_TLS=true
```

`GRAFANA_SECRET_KEY` harus random, panjang, dan tidak diganti sembarangan setelah Grafana berjalan.

## 5. Siapkan Folder Persistent

```bash
mkdir -p config/targets config/alertmanager
mkdir -p data/prometheus data/alertmanager data/grafana data/karma data/sla-reports data/alert-history
sudo chown -R 65534:65534 data/prometheus data/alertmanager
sudo chown -R 472:472 data/grafana
sudo chown -R $(id -u):$(id -g) config data/karma data/sla-reports data/alert-history
```

## 6. Isi Target Monitoring

Edit:

```bash
nano targets.yml
```

Contoh:

```yaml
servers:
  - name: server01
    address: 192.0.2.10
    labels:
      project: example-project
    exporters:
      node: true
      node_port: 9100
    probes:
      icmp: true
```

Label utama cukup:

```yaml
project: nama-project
```

Generator otomatis menambahkan:

```text
host
target_address
```

## 7. Install Node Exporter di Server Target

Jika Node Exporter manual via systemd, tambahkan flag:

```bash
--collector.systemd --collector.systemd.unit-include='(nginx|php.*fpm|mysql|mysqld|mariadb|redis|redis-server|docker|ssh|sshd)\.service'
```

Restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart prometheus-node-exporter
```

Validasi:

```bash
curl -s localhost:9100/metrics | grep node_systemd_unit_state
```

## 8. Jalankan Stack

Build image custom:

```bash
docker compose build
```

Generate target Prometheus:

```bash
docker compose run --rm file-sd-generator
```

Generate konfigurasi Alertmanager dari `.env`:

```bash
docker compose run --rm alertmanager-config
```

Start semua service:

```bash
docker compose up -d
```

Cek:

```bash
docker compose ps
```

## 9. Service yang Berjalan

Port lokal default:

```text
Grafana       127.0.0.1:3000
Prometheus    127.0.0.1:9090
Alertmanager  127.0.0.1:9093
Blackbox      127.0.0.1:9115
Karma         127.0.0.1:8080
Alert History 127.0.0.1:18080
Nginx         0.0.0.0:80 dan 0.0.0.0:443
```

Akses via Nginx:

```text
/grafana/
/prometheus/
/alertmanager/
/karma/
/history/
```

## 10. Nginx Reverse Proxy

Contoh location untuk Alert History:

```nginx
location /history/ {
  proxy_pass http://alert-history:8080;
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto https;
}

location = /history {
  return 301 /history/$is_args$args;
}
```

Contoh location Grafana:

```nginx
location = /grafana {
  return 301 /grafana/;
}

location /grafana/ {
  proxy_pass http://grafana:3000;
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto https;
}
```

## 11. Alert History

Alert History menyimpan event dari Alertmanager:

```text
firing
resolved
host
project
alertname
severity
starts_at
resolved_at
duration
```

Database:

```text
data/alert-history/alert-history.db
```

Endpoint:

```text
/history/
/history/api/alerts
/health
/webhook
```

Filter UI memakai query string di `/history/`, misalnya `?host=server01&status=firing&limit=50`. Redirect `/history` harus mempertahankan query string agar filter tidak hilang.

Test lokal:

```bash
curl http://127.0.0.1:18080/health
```

Test via domain:

```bash
curl -k -I https://monitoring.example.com/history/
```

## 12. Grafana Dashboard

Dashboard tersedia:

```text
Production Monitoring / Reusable Server Uptime and Resources
HRIS Monitoring / HRIS Nusawork Infrastructure
```

Dashboard HRIS berisi:

- Overview semua host
- Detail host terpilih
- CPU
- Memory
- Filesystem
- Disk I/O
- Network
- Service systemd
- Availability timeline

## 13. Query Penting

Availability 30 hari:

```promql
avg_over_time(host:up:probe_icmp{host="server01"}[30d]) * 100
```

Service down count:

```promql
sum(1 - node_systemd_unit_state{job="node",host=~"$host",state="active",name=~"(nginx|php.*fpm|mysql|mysqld|mariadb|redis|redis-server|docker|ssh|sshd)\\.service"}) or vector(0)
```

Service status timeline:

```promql
node_systemd_unit_state{job="node",host=~"$host",state="active",name=~"(nginx|php.*fpm|mysql|mysqld|mariadb|redis|redis-server|docker|ssh|sshd)\\.service"}
```

## 14. Update dari GitHub

```bash
cd /root/Monitoring-Stack
git fetch origin
git pull --ff-only origin master
docker compose build
docker compose run --rm file-sd-generator
docker compose run --rm alertmanager-config
docker compose up -d
```

Jika ingin menjaga `.env`, `data`, dan `nginx`, jangan hapus folder tersebut.

## 15. Backup

Backup minimal:

```bash
tar czf monitoring-backup-$(date +%F).tar.gz \
  .env targets.yml prometheus alertmanager blackbox karma grafana config nginx data
```

Yang paling penting:

```text
.env
targets.yml
data/prometheus
data/grafana
data/alertmanager
data/alert-history
config/alertmanager
nginx/configuration
```

## 16. Troubleshooting

Prometheus permission denied:

```bash
sudo chown -R 65534:65534 data/prometheus
docker compose up -d prometheus
```

Alertmanager masih membaca `${SMTP_SMARTHOST}`:

```bash
docker compose run --rm alertmanager-config
docker compose restart alertmanager
cat config/alertmanager/alertmanager.yml
```

Grafana dashboard tidak muncul:

```bash
docker compose logs --tail=100 grafana | grep -i dashboard
```

Alert History kosong:

```bash
docker compose logs -f alert-history
docker compose logs -f alertmanager
```

Cek webhook receiver:

```bash
grep -n 'alert-history\|webhook' config/alertmanager/alertmanager.yml
```
