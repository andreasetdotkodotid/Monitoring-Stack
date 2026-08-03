# Production Monitoring Stack Private Documentation

Stack ini menjalankan Prometheus, Grafana, Alertmanager, Karma, Blackbox Exporter, generator file_sd dari `targets.yml`, dan SLA reporter berbasis email.

## Struktur

```text
.
├── docker-compose.yml
├── .env.example
├── targets.yml
├── prometheus/
│   ├── prometheus.yml
│   └── rules/
│       ├── alerts.yml
│       └── recording.yml
├── alertmanager/alertmanager.yml
├── blackbox/config.yml
├── karma/karma.yml
├── grafana/
│   ├── provisioning/datasources/prometheus.yml
│   ├── provisioning/dashboards/dashboards.yml
│   └── dashboards/
│       ├── production/reusable-server-sla.json
│       └── hris/hris-nusawork-infrastructure.json
├── scripts/
│   ├── file-sd/
│   └── sla-report/
├── config/targets/
└── data/
```

## Desain

`targets.yml` adalah single source of truth. Container `file-sd-generator` mengubahnya menjadi file JSON Prometheus file service discovery:

- `node.json`
- `icmp.json`
- `http.json`
- `tcp.json`
- `nginx.json`

Prometheus tidak perlu diubah saat server baru ditambah. Label dari `targets.yml` otomatis masuk ke metric Prometheus dan digunakan untuk filter dashboard, alert, recording rules, dan SLA report.

`alertmanager/alertmanager.yml.tmpl` dirender oleh service `alertmanager-config` ke `config/alertmanager/alertmanager.yml` agar nilai SMTP dari `.env` benar-benar masuk ke konfigurasi Alertmanager. File hasil render berisi secret dan tidak boleh di-commit.

## Deployment awal

```bash
cp .env.example .env
nano .env
mkdir -p data/prometheus data/alertmanager data/grafana data/karma data/sla-reports config/targets config/alertmanager
sudo chown -R 65534:65534 data/prometheus data/alertmanager
sudo chown -R 472:472 data/grafana
sudo chown -R $(id -u):$(id -g) config data/karma data/sla-reports
docker compose build
docker compose up -d
```

Akses lokal default bind ke `127.0.0.1`. Untuk production, taruh reverse proxy Nginx/Caddy/Traefik di depan:

- `/grafana/` -> `127.0.0.1:3000`
- `/prometheus/` -> `127.0.0.1:9090`
- `/alertmanager/` -> `127.0.0.1:9093`
- `/karma/` -> `127.0.0.1:8080`

## Google OAuth Grafana

Buat OAuth Client di Google Cloud Console:

- Application type: Web application
- Authorized redirect URI: `https://monitoring.example.com/grafana/login/google`

Set di `.env`:

```env
GRAFANA_DOMAIN=monitoring.example.com
GRAFANA_ROOT_URL=https://monitoring.example.com/grafana/
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxx
GOOGLE_ALLOWED_DOMAINS=example.com
```

## Node Exporter pada server target

Cukup install Node Exporter di setiap server Linux.

Contoh Docker:

```bash
docker run -d --name node-exporter --restart unless-stopped \
  --net=host --pid=host \
  -v /:/host:ro,rslave \
  -v /run/systemd:/run/systemd:ro \
  -v /var/run/dbus/system_bus_socket:/var/run/dbus/system_bus_socket:ro \
  quay.io/prometheus/node-exporter:v1.8.2 \
  --path.rootfs=/host \
  --collector.systemd \
  --collector.systemd.unit-include='(nginx|php.*fpm|mysql|mysqld|mariadb|redis|redis-server|docker|ssh|sshd)\.service'
```

Pastikan port `9100/tcp` hanya dapat diakses dari server monitoring.

Jika Node Exporter diinstall manual via systemd, tambahkan flag berikut ke environment service, misalnya `/etc/default/prometheus-node-exporter` atau `/etc/default/node_exporter`:

```bash
--collector.systemd --collector.systemd.unit-include='(nginx|php.*fpm|mysql|mysqld|mariadb|redis|redis-server|docker|ssh|sshd)\.service'
```

Validasi service metric:

```bash
curl -s localhost:9100/metrics | grep node_systemd_unit_state
```

## targets.yml

Contoh server:

```yaml
servers:
  - name: web01
    address: 10.10.10.11
    labels:
      project: nusawork
    exporters:
      node: true
      node_port: 9100
    probes:
      icmp: true
      http:
        - https://hris.example.com
      tcp:
        - 22
        - 443
      nginx_status:
        - http://10.10.10.11/nginx_status
```

Tambah server cukup edit `targets.yml`, lalu watcher akan regenerate file_sd. Prometheus membaca ulang setiap 30 detik.

Jika perlu paksa regenerate:

```bash
docker compose run --rm file-sd-generator
curl -X POST http://127.0.0.1:9090/-/reload
```

## Tambah project baru

```yaml
  - name: api01
    address: 10.10.20.21
    labels:
      project: payroll
    exporters:
      node: true
    probes:
      icmp: true
      http:
        - https://payroll.example.com/health
      tcp:
        - 443
```

Dashboard otomatis bisa difilter dengan `project=payroll`.

## Scope monitoring

Stack ini difokuskan untuk uptime dan resource server:

- Uptime host via ICMP Blackbox
- Endpoint HTTP/HTTPS jika didefinisikan
- TCP port jika didefinisikan
- Resource Linux via Node Exporter

Monitoring Nginx spesifik dihapus agar label alert tetap bersih dan tidak mencampur status host dengan status service aplikasi.

## PromQL penting

Availability host 30 hari:

```promql
avg_over_time(host:up:probe_icmp{host="web01"}[30d]) * 100
```

SLA bulanan approximation 30 hari:

```promql
avg_over_time(host:up:probe_icmp{project="nusawork"}[30d]) * 100
```

Total downtime 30 hari detik:

```promql
(1 - avg_over_time(host:up:probe_icmp{host="web01"}[30d])) * 30 * 24 * 3600
```

Uptime seconds 30 hari:

```promql
avg_over_time(host:up:probe_icmp{host="web01"}[30d]) * 30 * 24 * 3600
```

Downtime events count:

```promql
changes(host:up:probe_icmp{host="web01"}[30d]) / 2
```

Server currently down since approximation:

```promql
timestamp(host:up:probe_icmp{host="web01"} == 0)
```

Catatan: Prometheus time series cocok untuk availability agregat. Untuk riwayat downtime dengan start, resolved, durasi yang presisi dan auditable, sumber terbaik adalah Alertmanager notification log atau event database. Stack ini menyediakan table source dari state changes dan SLA CSV. Untuk audit RFO formal, rekomendasi production adalah menambahkan alert webhook receiver kecil yang menyimpan alert firing/resolved ke PostgreSQL atau object storage.

## Alert

Alert dasar tersedia di `prometheus/rules/alerts.yml`:

- Host Down
- ICMP Down
- HTTP Down
- HTTPS Down
- TCP Port Down
- Service Down
- High CPU Usage
- High Memory Usage
- High Load Average
- Disk Usage High
- Filesystem Read Only
- Low Disk Inode
- OOM Killer
- Swap Usage High
- Node Exporter Down
- Blackbox Exporter Down

Semua alert membawa labels dari target.

## SLA email report

Service `sla-report` berjalan terus dan mengirim report pada jadwal cron `REPORT_CRON`, default `5 8 1 * *`.

Output CSV disimpan di `data/sla-reports` dan dikirim via SMTP.

## Backup

Backup minimal:

```bash
tar czf monitoring-backup-$(date +%F).tar.gz \
  .env targets.yml prometheus alertmanager blackbox karma grafana config data
```

Backup penting:

- `targets.yml`
- `.env`
- `prometheus/rules`
- `grafana/dashboards`
- `data/prometheus`
- `data/grafana`
- `data/alertmanager`
- `data/sla-reports`

## Security best practice

- Jangan expose Prometheus, Alertmanager, Karma langsung ke internet.
- Bind port ke `127.0.0.1` dan gunakan reverse proxy TLS.
- Proteksi `/prometheus`, `/alertmanager`, `/karma` dengan OAuth/basic auth/IP allowlist.
- Batasi akses Node Exporter port 9100 hanya dari monitoring server.
- Simpan `.env` sebagai secret private, jangan commit ke public repository.
- Gunakan Google OAuth allowed domains/groups.
- Rotate SMTP password dan OAuth client secret berkala.
- Jalankan backup terenkripsi.

## Maintenance dan upgrade

Prosedur upgrade aman:

```bash
docker compose pull
docker compose build --pull
docker compose up -d
```

Sebelum upgrade:

```bash
docker compose config
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
```

## Push ke GitHub private

```bash
git init
git add .
git status
git commit -m "Initial production monitoring stack"
gh repo create nusawork-monitoring --private --source=. --remote=origin --push
```

Pastikan `.env` tidak ikut commit. Gunakan `.env.example` saja.

## Push image custom ke Docker Hub

Image custom hanya untuk:

- `file-sd-generator`
- `sla-report`

```bash
docker login
docker build -t DOCKERHUB_USER/nusawork-file-sd-generator:1.0.0 scripts/file-sd
docker build -t DOCKERHUB_USER/nusawork-sla-report:1.0.0 scripts/sla-report
docker push DOCKERHUB_USER/nusawork-file-sd-generator:1.0.0
docker push DOCKERHUB_USER/nusawork-sla-report:1.0.0
```

Lalu ubah `docker-compose.yml` dari `build:` menjadi `image:` jika ingin pull dari Docker Hub.

## Update deployment via Git di server

Jika server sudah pernah deploy dan ada perubahan lokal, cek dulu:

```bash
cd /root/Monitoring-Stack
git status
```

Jika perubahan lokal hanya generated file atau konfigurasi yang ingin disamakan dengan repository:

```bash
cd /root/Monitoring-Stack
git fetch origin
git checkout -- docker-compose.yml prometheus alertmanager karma grafana scripts targets.yml
git pull --ff-only origin master
```

Render ulang file discovery dan Alertmanager config:

```bash
mkdir -p config/targets config/alertmanager data/prometheus data/alertmanager data/grafana data/karma data/sla-reports
sudo chown -R 65534:65534 data/prometheus data/alertmanager
sudo chown -R 472:472 data/grafana
sudo chown -R $(id -u):$(id -g) config data/karma data/sla-reports
docker compose down
docker compose build file-sd-generator file-sd-watcher sla-report alertmanager-config
docker compose run --rm file-sd-generator
docker compose run --rm alertmanager-config
docker compose up -d
```

Cek hasil:

```bash
docker compose ps
docker compose logs --tail=50 prometheus alertmanager
cat config/alertmanager/alertmanager.yml
```

Pastikan `config/alertmanager/alertmanager.yml` tidak berisi literal `${SMTP_SMARTHOST}`.

## Trade-off penting

- `targets.yml` custom tidak bisa dibaca langsung oleh native `file_sd_configs`, karena Prometheus butuh JSON/YAML array file_sd format. Karena itu digunakan generator kecil agar format input tetap human-friendly.
- Riwayat downtime lengkap lebih tepat disimpan sebagai event log. Prometheus bisa menghitung availability dan perubahan state, tetapi bukan database event audit.
- Untuk skala sangat besar, gunakan shard Prometheus atau Thanos/Mimir untuk long-term storage.
