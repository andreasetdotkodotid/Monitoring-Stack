# Monitoring Stack

Production-oriented monitoring stack berbasis Docker Compose untuk server Linux.

Stack ini menggunakan Prometheus ecosystem:

- Prometheus
- Grafana
- Alertmanager
- Karma
- Blackbox Exporter
- Node Exporter di server target
- Nginx reverse proxy

## Fitur

- Monitoring uptime host via ICMP.
- Monitoring resource Linux via Node Exporter.
- Monitoring service systemd via Node Exporter systemd collector.
- Dashboard Grafana reusable.
- Dashboard HRIS Infrastructure dengan overview dan detail host.
- Alert dasar untuk host, exporter, resource, service, dan port.
- SLA report bulanan via email.
- Target server dikelola dari satu file `targets.yml`.
- Persistent data memakai bind mount.

## Struktur Singkat

```text
.
├── docker-compose.yml
├── targets.yml
├── prometheus/
├── alertmanager/
├── blackbox/
├── karma/
├── grafana/
├── scripts/
├── config/
├── data/
└── docs/
```

## Quick Start

```bash
cp .env.example .env
nano .env
mkdir -p config/targets config/alertmanager
mkdir -p data/prometheus data/alertmanager data/grafana data/karma data/sla-reports
sudo chown -R 65534:65534 data/prometheus data/alertmanager
sudo chown -R 472:472 data/grafana
docker compose build
docker compose run --rm file-sd-generator
docker compose run --rm alertmanager-config
docker compose up -d
```

Cek status:

```bash
docker compose ps
```

## targets.yml

Contoh target aman untuk repository:

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

Untuk production, ganti `name`, `address`, dan `project` sesuai server kamu.

## Node Exporter di Server Target

Node Exporter harus expose port `9100`.

Jika ingin monitoring service systemd, aktifkan:

```bash
--collector.systemd --collector.systemd.unit-include='(nginx|php.*fpm|mysql|mysqld|mariadb|redis|redis-server|docker|ssh|sshd)\.service'
```

## Dashboard

Dashboard yang disediakan:

- `Production Monitoring / Reusable Server Uptime and Resources`
- `HRIS Monitoring / HRIS Nusawork Infrastructure`

## Dokumentasi

Dokumentasi detail ada di:

```text
docs/PRIVATE_MONITORING_RUNBOOK.md
docs/MANUAL_INSTALL_TUTORIAL.md
```

## Security Notes

- Jangan commit `.env`.
- Jangan expose Prometheus dan Alertmanager langsung ke internet.
- Batasi akses Node Exporter port `9100` hanya dari server monitoring.
- Gunakan TLS dan OAuth untuk akses Grafana.
- Gunakan fake IP untuk contoh public repository.

## License

Private/internal use.
