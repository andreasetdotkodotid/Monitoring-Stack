# Tutorial Manual Install Monitoring Stack Tanpa Docker

Dokumen ini menjelaskan cara memasang Prometheus, Grafana, Alertmanager, Blackbox Exporter, Node Exporter, dan dashboard secara manual memakai systemd.

Panduan ini cocok untuk belajar konsep dasar tanpa Docker Compose.

Contoh OS: Ubuntu/Debian.

## 1. Arsitektur Manual

Server monitoring menjalankan:

- Prometheus
- Grafana
- Alertmanager
- Blackbox Exporter
- Nginx reverse proxy opsional

Server target menjalankan:

- Node Exporter

Alur data:

```text
Node Exporter -> Prometheus -> Grafana
Blackbox Exporter -> Prometheus -> Grafana
Prometheus Alerts -> Alertmanager -> Email/Karma
```

## 2. User System

Buat user service:

```bash
sudo useradd --no-create-home --shell /usr/sbin/nologin prometheus
sudo useradd --no-create-home --shell /usr/sbin/nologin alertmanager
sudo useradd --no-create-home --shell /usr/sbin/nologin blackbox_exporter
sudo useradd --no-create-home --shell /usr/sbin/nologin node_exporter
```

## 3. Install Prometheus

Download Prometheus:

```bash
cd /tmp
wget https://github.com/prometheus/prometheus/releases/download/v2.54.1/prometheus-2.54.1.linux-amd64.tar.gz
tar xzf prometheus-2.54.1.linux-amd64.tar.gz
cd prometheus-2.54.1.linux-amd64
```

Install binary:

```bash
sudo cp prometheus promtool /usr/local/bin/
sudo mkdir -p /etc/prometheus/rules /etc/prometheus/targets /var/lib/prometheus
sudo cp consoles console_libraries /etc/prometheus/ -r
sudo chown -R prometheus:prometheus /etc/prometheus /var/lib/prometheus
```

Buat config:

```bash
sudo nano /etc/prometheus/prometheus.yml
```

Isi contoh:

```yaml
global:
  scrape_interval: 30s
  scrape_timeout: 10s
  evaluation_interval: 30s

rule_files:
  - /etc/prometheus/rules/*.yml

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - 127.0.0.1:9093

scrape_configs:
  - job_name: prometheus
    static_configs:
      - targets: [127.0.0.1:9090]
        labels:
          project: monitoring
          service: prometheus
          host: prometheus

  - job_name: node
    file_sd_configs:
      - files:
          - /etc/prometheus/targets/node.json
        refresh_interval: 30s

  - job_name: blackbox_icmp
    metrics_path: /probe
    params:
      module: [icmp]
    file_sd_configs:
      - files:
          - /etc/prometheus/targets/icmp.json
        refresh_interval: 30s
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: 127.0.0.1:9115
```

Buat file target Node Exporter:

```bash
sudo nano /etc/prometheus/targets/node.json
```

Isi:

```json
[
  {
    "targets": ["192.0.2.10:9100"],
    "labels": {
      "project": "example-project",
      "host": "server01",
      "target_address": "192.0.2.10"
    }
  }
]
```

Buat file target ICMP:

```bash
sudo nano /etc/prometheus/targets/icmp.json
```

Isi:

```json
[
  {
    "targets": ["192.0.2.10"],
    "labels": {
      "project": "example-project",
      "host": "server01",
      "target_address": "192.0.2.10"
    }
  }
]
```

Buat systemd service:

```bash
sudo nano /etc/systemd/system/prometheus.service
```

Isi:

```ini
[Unit]
Description=Prometheus
Wants=network-online.target
After=network-online.target

[Service]
User=prometheus
Group=prometheus
Type=simple
ExecStart=/usr/local/bin/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/var/lib/prometheus \
  --storage.tsdb.retention.time=180d \
  --web.enable-lifecycle
Restart=always

[Install]
WantedBy=multi-user.target
```

Start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now prometheus
sudo systemctl status prometheus
```

Cek:

```bash
curl http://127.0.0.1:9090/-/ready
```

## 4. Install Blackbox Exporter

Download:

```bash
cd /tmp
wget https://github.com/prometheus/blackbox_exporter/releases/download/v0.25.0/blackbox_exporter-0.25.0.linux-amd64.tar.gz
tar xzf blackbox_exporter-0.25.0.linux-amd64.tar.gz
cd blackbox_exporter-0.25.0.linux-amd64
sudo cp blackbox_exporter /usr/local/bin/
sudo mkdir -p /etc/blackbox_exporter
sudo chown -R blackbox_exporter:blackbox_exporter /etc/blackbox_exporter
```

Config:

```bash
sudo nano /etc/blackbox_exporter/config.yml
```

Isi:

```yaml
modules:
  icmp:
    prober: icmp
    timeout: 5s
    icmp:
      preferred_ip_protocol: ip4

  http_2xx:
    prober: http
    timeout: 10s
    http:
      method: GET
      preferred_ip_protocol: ip4
      follow_redirects: true

  tcp_connect:
    prober: tcp
    timeout: 5s
    tcp:
      preferred_ip_protocol: ip4
```

Permission ICMP:

Blackbox Exporter module `icmp` butuh izin raw ICMP socket. Karena service dijalankan sebagai user non-root `blackbox_exporter`, binary harus diberi Linux capability `cap_net_raw`.

Install paket capability jika belum ada:

```bash
sudo apt-get update
sudo apt-get install -y libcap2-bin
```

Berikan permission raw socket ke binary:

```bash
sudo setcap cap_net_raw+ep /usr/local/bin/blackbox_exporter
```

Pastikan capability sudah terpasang:

```bash
getcap /usr/local/bin/blackbox_exporter
```

Output yang benar:

```text
/usr/local/bin/blackbox_exporter cap_net_raw=ep
```

Kenapa ini wajib?

```text
probe_success = 0
```

bisa terjadi bukan karena host target mati, tapi karena Blackbox Exporter tidak diizinkan membuat ICMP socket. Biasanya log berisi error seperti `operation not permitted` atau `socket: permission denied`.

Systemd:

```bash
sudo nano /etc/systemd/system/blackbox_exporter.service
```

Isi:

```ini
[Unit]
Description=Blackbox Exporter
After=network-online.target
Wants=network-online.target

[Service]
User=blackbox_exporter
Group=blackbox_exporter
ExecStart=/usr/local/bin/blackbox_exporter --config.file=/etc/blackbox_exporter/config.yml
Restart=always
RestartSec=5
NoNewPrivileges=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/tmp
AmbientCapabilities=CAP_NET_RAW
CapabilityBoundingSet=CAP_NET_RAW

[Install]
WantedBy=multi-user.target
```

Catatan permission:

- `setcap cap_net_raw+ep` memberi izin ICMP langsung ke binary.
- `AmbientCapabilities=CAP_NET_RAW` memastikan capability tetap tersedia saat binary dijalankan oleh systemd sebagai user non-root.
- `CapabilityBoundingSet=CAP_NET_RAW` membatasi capability service hanya ke raw socket.
- Jika memakai systemd hardening yang lebih ketat, jangan hapus `AmbientCapabilities`.

Start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now blackbox_exporter
sudo systemctl status blackbox_exporter
```

Test langsung ke Blackbox Exporter:

```bash
curl 'http://127.0.0.1:9115/probe?target=8.8.8.8&module=icmp'
```

Hasil yang benar harus berisi:

```text
probe_success 1
```

Jika masih `probe_success 0`, cek debug output:

```bash
curl 'http://127.0.0.1:9115/probe?target=8.8.8.8&module=icmp&debug=true'
```

Cek log service:

```bash
sudo journalctl -u blackbox_exporter -n 100 --no-pager
```

Jika ada error permission, ulangi:

```bash
sudo setcap cap_net_raw+ep /usr/local/bin/blackbox_exporter
getcap /usr/local/bin/blackbox_exporter
sudo systemctl restart blackbox_exporter
```

Jika binary diganti saat upgrade, `setcap` harus dijalankan ulang karena capability menempel ke file binary.

## 5. Install Alertmanager

Download:

```bash
cd /tmp
wget https://github.com/prometheus/alertmanager/releases/download/v0.27.0/alertmanager-0.27.0.linux-amd64.tar.gz
tar xzf alertmanager-0.27.0.linux-amd64.tar.gz
cd alertmanager-0.27.0.linux-amd64
sudo cp alertmanager amtool /usr/local/bin/
sudo mkdir -p /etc/alertmanager /var/lib/alertmanager
sudo chown -R alertmanager:alertmanager /etc/alertmanager /var/lib/alertmanager
```

Config:

```bash
sudo nano /etc/alertmanager/alertmanager.yml
```

Isi contoh:

```yaml
route:
  receiver: email-default
  group_by: [alertname, project, service, host]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h

receivers:
  - name: email-default
    email_configs:
      - to: sre@example.com
        from: monitoring@example.com
        smarthost: smtp.example.com:587
        auth_username: monitoring@example.com
        auth_password: change-me
        require_tls: true
        send_resolved: true
```

Systemd:

```bash
sudo nano /etc/systemd/system/alertmanager.service
```

Isi:

```ini
[Unit]
Description=Alertmanager
After=network-online.target

[Service]
User=alertmanager
Group=alertmanager
ExecStart=/usr/local/bin/alertmanager \
  --config.file=/etc/alertmanager/alertmanager.yml \
  --storage.path=/var/lib/alertmanager
Restart=always

[Install]
WantedBy=multi-user.target
```

Start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now alertmanager
curl http://127.0.0.1:9093/-/ready
```

## 6. Recording Rules dan Alert Rules

Buat rules:

```bash
sudo nano /etc/prometheus/rules/recording.yml
```

Isi:

```yaml
groups:
  - name: availability.recording
    interval: 30s
    rules:
      - record: host:up:probe_icmp
        expr: max by (project, host) (probe_success{job="blackbox_icmp"})

      - record: host:up:node
        expr: max by (project, host) (up{job="node"})

      - record: host:availability_30d:ratio
        expr: avg_over_time(host:up:probe_icmp[30d])

      - record: host:downtime_30d:seconds
        expr: (1 - avg_over_time(host:up:probe_icmp[30d])) * 30 * 24 * 3600

  - name: node.recording
    interval: 30s
    rules:
      - record: node:cpu_usage:ratio
        expr: 1 - avg by (project, host) (rate(node_cpu_seconds_total{job="node",mode="idle"}[5m]))

      - record: node:memory_usage:ratio
        expr: 1 - (node_memory_MemAvailable_bytes{job="node"} / node_memory_MemTotal_bytes{job="node"})

      - record: node:filesystem_usage:ratio
        expr: 1 - (node_filesystem_avail_bytes{job="node",fstype!~"tmpfs|fuse.lxcfs|overlay|squashfs",mountpoint!~"/run.*|/var/lib/docker/.*"} / node_filesystem_size_bytes{job="node",fstype!~"tmpfs|fuse.lxcfs|overlay|squashfs",mountpoint!~"/run.*|/var/lib/docker/.*"})
```

Buat alert:

```bash
sudo nano /etc/prometheus/rules/alerts.yml
```

Isi ringkas:

```yaml
groups:
  - name: alerts
    rules:
      - alert: HostDown
        expr: host:up:probe_icmp == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: Host {{ $labels.host }} is down

      - alert: NodeExporterDown
        expr: host:up:node == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: Node Exporter down on {{ $labels.host }}

      - alert: ServiceDown
        expr: node_systemd_unit_state{job="node",state="active",name=~"(nginx|php.*fpm|mysql|mysqld|mariadb|redis|redis-server|docker|ssh|sshd)\\.service"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: Service {{ $labels.name }} down on {{ $labels.host }}
```

Validasi:

```bash
promtool check config /etc/prometheus/prometheus.yml
sudo systemctl reload prometheus
```

Jika reload gagal:

```bash
curl -X POST http://127.0.0.1:9090/-/reload
```

## 7. Install Node Exporter di Server Target

Download:

```bash
cd /tmp
wget https://github.com/prometheus/node_exporter/releases/download/v1.8.2/node_exporter-1.8.2.linux-amd64.tar.gz
tar xzf node_exporter-1.8.2.linux-amd64.tar.gz
cd node_exporter-1.8.2.linux-amd64
sudo cp node_exporter /usr/local/bin/
```

Systemd:

```bash
sudo nano /etc/systemd/system/node_exporter.service
```

Isi:

```ini
[Unit]
Description=Node Exporter
After=network-online.target

[Service]
User=node_exporter
Group=node_exporter
ExecStart=/usr/local/bin/node_exporter \
  --collector.systemd \
  --collector.systemd.unit-include='(nginx|php.*fpm|mysql|mysqld|mariadb|redis|redis-server|docker|ssh|sshd)\.service'
Restart=always

[Install]
WantedBy=multi-user.target
```

Start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now node_exporter
curl -s localhost:9100/metrics | grep node_systemd_unit_state
```

## 8. Install Grafana

Tambahkan repository:

```bash
sudo apt-get install -y apt-transport-https software-properties-common wget gpg
sudo mkdir -p /etc/apt/keyrings
wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/grafana.gpg > /dev/null
echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee /etc/apt/sources.list.d/grafana.list
sudo apt-get update
sudo apt-get install -y grafana
```

Start:

```bash
sudo systemctl enable --now grafana-server
sudo systemctl status grafana-server
```

Akses:

```text
http://server-monitoring:3000
```

Login default:

```text
admin / admin
```

Segera ganti password.

## 9. Tambahkan Datasource Prometheus di Grafana

Bisa lewat UI:

1. Login Grafana.
2. Buka Connections > Data sources.
3. Add data source.
4. Pilih Prometheus.
5. URL:

```text
http://127.0.0.1:9090
```

6. Save & Test.

Atau provisioning manual:

```bash
sudo mkdir -p /etc/grafana/provisioning/datasources
sudo nano /etc/grafana/provisioning/datasources/prometheus.yml
```

Isi:

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://127.0.0.1:9090
    isDefault: true
    editable: true
    jsonData:
      timeInterval: 30s
      httpMethod: POST
```

Restart:

```bash
sudo systemctl restart grafana-server
```

## 10. Cara Bikin Dashboard Seperti Sekarang

Dashboard sekarang punya konsep dua row:

1. Infrastructure Overview
2. Selected Host Detail

### 10.1 Variable datasource

Di dashboard settings > Variables > New:

```text
Name: datasource
Type: Datasource
Plugin: Prometheus
Hide: Variable
```

Semua panel gunakan datasource ini.

### 10.2 Variable host

Tambah variable:

```text
Name: host
Type: Query
Datasource: $datasource
Query: label_values(host:up:node, host)
Multi-value: false
Include All: false
Sort: Alphabetical ascending
Refresh: On dashboard load
```

### 10.3 Row 1 Overview

Panel Stat:

Total Hosts:

```promql
count(host:up:probe_icmp)
```

Hosts Up:

```promql
sum(host:up:probe_icmp)
```

Hosts Down:

```promql
count(host:up:probe_icmp) - sum(host:up:probe_icmp)
```

Exporters Down:

```promql
count(host:up:node) - sum(host:up:node)
```

Services Down:

```promql
sum(1 - node_systemd_unit_state{job="node",state="active",name=~"(nginx|php.*fpm|mysql|mysqld|mariadb|redis|redis-server|docker|ssh|sshd)\\.service"}) or vector(0)
```

Lowest Host SLA:

```promql
min(host:availability_30d:ratio) * 100
```

Host Availability Timeline:

```promql
host:up:probe_icmp
```

Top CPU:

```promql
topk(5, node:cpu_usage:ratio * 100)
```

Top Memory:

```promql
topk(5, node:memory_usage:ratio * 100)
```

Top Filesystem:

```promql
topk(5, node:filesystem_usage:ratio * 100)
```

### 10.4 Row 2 Selected Host Detail

Semua query di Row 2 wajib pakai:

```promql
host="$host"
```

Host Status:

```promql
host:up:probe_icmp{host="$host"}
```

Exporter Status:

```promql
host:up:node{host="$host"}
```

Server Uptime:

```promql
time() - node_boot_time_seconds{job="node",host="$host"}
```

ICMP Latency:

```promql
probe_duration_seconds{job="blackbox_icmp",host="$host"} * 1000
```

Host SLA:

```promql
host:availability_30d:ratio{host="$host"} * 100
```

CPU Usage:

```promql
node:cpu_usage:ratio{host="$host"} * 100
```

Memory Usage:

```promql
node:memory_usage:ratio{host="$host"} * 100
```

Filesystem Usage:

```promql
node:filesystem_usage:ratio{host="$host"} * 100
```

Important Service Status:

```promql
node_systemd_unit_state{job="node",host=~"$host",state="active",name=~"(nginx|php.*fpm|mysql|mysqld|mariadb|redis|redis-server|docker|ssh|sshd)\\.service"}
```

Service Down Count:

```promql
sum(1 - node_systemd_unit_state{job="node",host=~"$host",state="active",name=~"(nginx|php.*fpm|mysql|mysqld|mariadb|redis|redis-server|docker|ssh|sshd)\\.service"}) or vector(0)
```

## 11. Visual Style Dashboard

Gunakan aturan sederhana:

- Status sehat: hijau.
- Status down: merah.
- Warning resource: kuning mulai 80%.
- Critical resource: merah mulai 90%.
- Time series pakai line width 2.
- Fill opacity 10-15%.
- Jangan tampilkan terlalu banyak series dalam satu panel.
- Row 1 jangan filter host.
- Row 2 wajib filter host.

## 12. Import Dashboard JSON

Jika punya file JSON dashboard:

1. Grafana > Dashboards > New > Import.
2. Upload JSON.
3. Pilih datasource Prometheus.
4. Import.

Atau provisioning:

```bash
sudo mkdir -p /var/lib/grafana/dashboards/hris
sudo cp hris-nusawork-infrastructure.json /var/lib/grafana/dashboards/hris/
sudo chown -R grafana:grafana /var/lib/grafana/dashboards
```

Provisioning provider:

```bash
sudo nano /etc/grafana/provisioning/dashboards/dashboards.yml
```

Isi:

```yaml
apiVersion: 1

providers:
  - name: HRIS Monitoring
    orgId: 1
    folder: HRIS Monitoring
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards/hris
```

Restart:

```bash
sudo systemctl restart grafana-server
```

## 13. Nginx Reverse Proxy Manual

Install:

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

Config:

```bash
sudo nano /etc/nginx/sites-available/monitoring.conf
```

Isi contoh:

```nginx
server {
  listen 80;
  server_name monitoring.example.com;
  return 301 https://$host$request_uri;
}

server {
  listen 443 ssl http2;
  server_name monitoring.example.com;

  ssl_certificate /etc/letsencrypt/live/monitoring.example.com/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/monitoring.example.com/privkey.pem;

  location /grafana/ {
    proxy_pass http://127.0.0.1:3000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto https;
  }

  location /prometheus/ {
    proxy_pass http://127.0.0.1:9090/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto https;
  }

  location /alertmanager/ {
    proxy_pass http://127.0.0.1:9093/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto https;
  }
}
```

Enable:

```bash
sudo ln -s /etc/nginx/sites-available/monitoring.conf /etc/nginx/sites-enabled/monitoring.conf
sudo nginx -t
sudo systemctl reload nginx
```

## 14. Alert History Manual Opsional

Pada instalasi manual, Alert History bisa dijalankan sebagai service Python kecil yang menerima webhook Alertmanager dan menyimpan data ke SQLite.

Buat folder:

```bash
sudo mkdir -p /opt/alert-history /var/lib/alert-history
sudo cp scripts/alert-history/app.py /opt/alert-history/app.py
sudo chown -R www-data:www-data /var/lib/alert-history
```

Buat service:

```bash
sudo nano /etc/systemd/system/alert-history.service
```

Isi:

```ini
[Unit]
Description=Alert History
After=network-online.target

[Service]
User=www-data
Group=www-data
Environment=DB_PATH=/var/lib/alert-history/alert-history.db
Environment=LISTEN_ADDR=127.0.0.1
Environment=LISTEN_PORT=18080
ExecStart=/usr/bin/python3 /opt/alert-history/app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now alert-history
curl http://127.0.0.1:18080/health
```

Tambahkan receiver Alertmanager:

```yaml
receivers:
  - name: alert-history
    webhook_configs:
      - url: http://127.0.0.1:18080/webhook
        send_resolved: true
```

Tambahkan route dengan `continue: true` agar email tetap jalan:

```yaml
route:
  routes:
    - receiver: alert-history
      continue: true
      matchers:
        - alertname=~".+"
```

Akses halaman:

```text
http://127.0.0.1:18080/history
```

Database tersimpan di:

```text
/var/lib/alert-history/alert-history.db
```

## 15. Troubleshooting Manual

Prometheus config error:

```bash
promtool check config /etc/prometheus/prometheus.yml
journalctl -u prometheus -f
```

Blackbox ICMP `probe_success` tetap `0`:

```bash
getcap /usr/local/bin/blackbox_exporter
systemctl cat blackbox_exporter
curl 'http://127.0.0.1:9115/probe?target=8.8.8.8&module=icmp&debug=true'
journalctl -u blackbox_exporter -n 100 --no-pager
```

Pastikan output `getcap` seperti ini:

```text
/usr/local/bin/blackbox_exporter cap_net_raw=ep
```

Pastikan systemd service punya:

```ini
AmbientCapabilities=CAP_NET_RAW
CapabilityBoundingSet=CAP_NET_RAW
```

Jika belum, perbaiki permission lalu restart:

```bash
sudo setcap cap_net_raw+ep /usr/local/bin/blackbox_exporter
sudo systemctl daemon-reload
sudo systemctl restart blackbox_exporter
```

Node Exporter tidak ada systemd metric:

```bash
systemctl cat node_exporter
curl -s localhost:9100/metrics | grep node_systemd_unit_state
```

Grafana dashboard tidak muncul:

```bash
journalctl -u grafana-server -f
ls -la /var/lib/grafana/dashboards/hris
```

Alertmanager email gagal:

```bash
journalctl -u alertmanager -f
amtool check-config /etc/alertmanager/alertmanager.yml
```

## 16. Ringkasan

Manual install memberi pemahaman lebih dalam karena semua komponen terlihat jelas:

- Binary ada di `/usr/local/bin`.
- Config ada di `/etc`.
- Data ada di `/var/lib`.
- Service dikontrol systemd.

Untuk production yang mudah dimaintain, Docker Compose tetap lebih praktis. Untuk belajar, manual install sangat bagus karena kamu memahami komponen Prometheus ecosystem satu per satu.
