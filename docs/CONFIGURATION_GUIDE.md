# Guide Konfigurasi Prometheus dan Rules

Dokumen ini menjelaskan konfigurasi Prometheus di project ini dengan bahasa sederhana.

Fokus utama:

- apa fungsi `prometheus/prometheus.yml`
- perbedaan `job_name: prometheus`, `job_name: node`, dan `job_name: blackbox_*`
- kenapa ada Blackbox Exporter
- apa itu recording rules
- kenapa bisa muncul metric baru seperti `host:up:probe_icmp`
- bagaimana alert rules memakai metric mentah dan metric hasil recording

## 1. Gambaran Besar Alur Monitoring

Alur sederhananya seperti ini:

```text
targets.yml
  ↓
file-sd-generator
  ↓
config/targets/*.json
  ↓
Prometheus scrape target
  ↓
metric mentah tersimpan di Prometheus
  ↓
recording rules membuat metric turunan
  ↓
Grafana dan alert rules memakai metric tersebut
  ↓
Alertmanager menerima alert dari Prometheus
```

Contoh file yang terlibat:

```text
targets.yml
scripts/file-sd/generate.py
config/targets/node.json
config/targets/icmp.json
config/targets/http.json
config/targets/tcp.json
prometheus/prometheus.yml
prometheus/rules/recording.yml
prometheus/rules/alerts.yml
```

## 2. Apa Fungsi `prometheus/prometheus.yml`

File ini adalah konfigurasi utama Prometheus.

Di project ini isinya terbagi menjadi 4 bagian besar:

```yaml
global:
  scrape_interval: 30s
  scrape_timeout: 10s
  evaluation_interval: 30s
```

Artinya:

- Prometheus mengambil metric setiap 30 detik.
- Kalau target tidak menjawab dalam 10 detik, scrape dianggap gagal.
- Rules dievaluasi setiap 30 detik.

```yaml
rule_files:
  - /etc/prometheus/rules/*.yml
```

Artinya Prometheus membaca semua rules dari folder:

```text
prometheus/rules/
```

Di project ini ada:

```text
prometheus/rules/recording.yml
prometheus/rules/alerts.yml
```

```yaml
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093
```

Artinya kalau ada alert firing, Prometheus mengirim alert tersebut ke service `alertmanager` port `9093`.

```yaml
scrape_configs:
```

Bagian ini berisi daftar target yang akan di-scrape oleh Prometheus.

## 3. Apa Itu `job_name`

`job_name` adalah nama kelompok scrape di Prometheus.

Setiap metric yang diambil oleh Prometheus otomatis mendapat label:

```text
job="nama_job"
```

Contoh:

```yaml
- job_name: prometheus
```

Metric dari job ini akan punya label:

```text
job="prometheus"
```

Contoh lain:

```yaml
- job_name: node
```

Metric dari job ini akan punya label:

```text
job="node"
```

Label `job` penting karena banyak query PromQL menggunakan filter ini.

Contoh:

```promql
up{job="node"}
```

Artinya:

```text
ambil metric up, tapi hanya dari job node
```

## 4. Perbedaan `job_name: prometheus` dan `job_name: blackbox_*`

Ini bagian yang sering membingungkan.

### 4.1 `job_name: prometheus`

Konfigurasi:

```yaml
- job_name: prometheus
  static_configs:
    - targets: [prometheus:9090]
      labels:
        project: monitoring
        service: prometheus
        host: prometheus
```

Artinya Prometheus memonitor dirinya sendiri.

Target yang di-scrape:

```text
prometheus:9090
```

Prometheus punya endpoint metric sendiri:

```text
/metrics
```

Jadi Prometheus mengambil metric dari:

```text
http://prometheus:9090/metrics
```

Contoh metric dari job ini:

```text
prometheus_http_requests_total
prometheus_tsdb_head_series
prometheus_rule_evaluation_duration_seconds
up{job="prometheus"}
```

Tujuannya:

- tahu apakah Prometheus sendiri hidup
- tahu performa Prometheus
- tahu jumlah series, rule evaluation, storage, dan lain-lain

### 4.2 `job_name: alertmanager`

Konfigurasi:

```yaml
- job_name: alertmanager
  static_configs:
    - targets: [alertmanager:9093]
```

Artinya Prometheus memonitor Alertmanager.

Prometheus scrape:

```text
http://alertmanager:9093/metrics
```

Tujuannya:

- tahu apakah Alertmanager hidup
- tahu status notification, silences, dan internal Alertmanager

### 4.3 `job_name: blackbox-exporter`

Konfigurasi:

```yaml
- job_name: blackbox-exporter
  static_configs:
    - targets: [blackbox-exporter:9115]
```

Ini memonitor service Blackbox Exporter itu sendiri.

Prometheus scrape:

```text
http://blackbox-exporter:9115/metrics
```

Ini belum mengecek host lain.

Ini hanya memastikan Blackbox Exporter hidup.

Contoh alert yang memakai job ini:

```promql
up{job="blackbox-exporter"} == 0
```

Kalau ini firing, artinya Blackbox Exporter mati atau tidak bisa di-scrape.

### 4.4 `job_name: blackbox_icmp`

Konfigurasi:

```yaml
- job_name: blackbox_icmp
  metrics_path: /probe
  params:
    module: [icmp]
  file_sd_configs:
    - files:
        - /etc/prometheus/targets/icmp.json
```

Ini bukan memonitor Blackbox Exporter-nya.

Ini memakai Blackbox Exporter untuk melakukan ping ICMP ke server target.

Alurnya:

```text
Prometheus
  ↓ request /probe?module=icmp&target=IP_TARGET
Blackbox Exporter
  ↓ ping ICMP
Server target
```

Hasilnya disimpan Prometheus sebagai metric:

```text
probe_success{job="blackbox_icmp", host="server01", project="example-project"}
```

Nilainya:

```text
1 = ping berhasil
0 = ping gagal
```

Jadi perbedaannya:

| Job | Yang Dicek | Endpoint | Hasil Utama |
|---|---|---|---|
| `prometheus` | Prometheus sendiri | `/metrics` | metric internal Prometheus |
| `alertmanager` | Alertmanager sendiri | `/metrics` | metric internal Alertmanager |
| `blackbox-exporter` | Blackbox Exporter sendiri | `/metrics` | apakah exporter hidup |
| `blackbox_icmp` | host target via ping | `/probe` | `probe_success` |
| `blackbox_http` | URL HTTP/HTTPS | `/probe` | `probe_success` |
| `blackbox_tcp` | port TCP | `/probe` | `probe_success` |

## 5. Perbedaan Node Exporter dan Blackbox Exporter

### Node Exporter

Node Exporter dipasang di server target.

Prometheus mengambil metric langsung dari server target:

```text
Prometheus → server01:9100/metrics
```

Node Exporter menjawab pertanyaan seperti:

- CPU berapa persen?
- RAM berapa persen?
- Disk penuh atau tidak?
- Filesystem read-only atau tidak?
- Load average berapa?
- Service systemd aktif atau tidak?

Contoh metric:

```text
node_cpu_seconds_total
node_memory_MemAvailable_bytes
node_filesystem_avail_bytes
node_systemd_unit_state
```

### Blackbox Exporter

Blackbox Exporter tidak perlu dipasang di server target.

Blackbox Exporter berjalan di server monitoring.

Prometheus meminta Blackbox Exporter mengecek target dari luar:

```text
Prometheus → Blackbox Exporter → ping/server/url/port target
```

Blackbox Exporter menjawab pertanyaan seperti:

- host bisa diping atau tidak?
- website HTTP/HTTPS bisa dibuka atau tidak?
- port TCP terbuka atau tidak?

Contoh metric:

```text
probe_success
probe_duration_seconds
probe_http_status_code
```

### Ringkasnya

| Exporter | Dipasang di Target? | Fungsi |
|---|---:|---|
| Node Exporter | Ya | melihat kondisi internal server |
| Blackbox Exporter | Tidak | mengecek target dari luar |

Contoh analogi:

```text
Node Exporter = dokter di dalam server
Blackbox Exporter = orang luar yang mengetuk pintu server
```

Kalau ICMP down tapi Node Exporter masih up, mungkin ping diblokir firewall.

Kalau Node Exporter down tapi ICMP up, server masih hidup tapi Node Exporter mati atau port 9100 tertutup.

Kalau keduanya down, server kemungkinan benar-benar unreachable.

## 6. Dari `targets.yml` Menjadi Target Prometheus

File utama target ada di:

```text
targets.yml
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

File ini tidak dibaca langsung oleh Prometheus.

Project ini punya generator:

```text
scripts/file-sd/generate.py
```

Generator mengubah `targets.yml` menjadi file JSON:

```text
config/targets/node.json
config/targets/icmp.json
config/targets/http.json
config/targets/tcp.json
```

Contoh hasil untuk Node Exporter:

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

Contoh hasil untuk ICMP:

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

Prometheus membaca file JSON ini lewat:

```yaml
file_sd_configs:
  - files:
      - /etc/prometheus/targets/node.json
```

`file_sd` artinya file service discovery.

Jadi kalau mau tambah server, cukup edit `targets.yml`, lalu regenerate file target.

## 7. Cara Kerja `blackbox_icmp` dan `relabel_configs`

Bagian ini penting.

Konfigurasi `blackbox_icmp`:

```yaml
- job_name: blackbox_icmp
  metrics_path: /probe
  params:
    module: [icmp]
  file_sd_configs:
    - files:
        - /etc/prometheus/targets/icmp.json
  relabel_configs:
    - source_labels: [__address__]
      target_label: __param_target
    - source_labels: [__param_target]
      target_label: instance
    - target_label: __address__
      replacement: blackbox-exporter:9115
```

Misalnya dari `icmp.json` ada target:

```text
192.0.2.10
```

Awalnya Prometheus menganggap target scrape adalah:

```text
192.0.2.10
```

Tapi untuk Blackbox, Prometheus tidak boleh scrape langsung ke `192.0.2.10/metrics`.

Prometheus harus scrape ke Blackbox Exporter:

```text
blackbox-exporter:9115/probe
```

Lalu IP target asli dikirim sebagai parameter:

```text
/probe?module=icmp&target=192.0.2.10
```

Itulah fungsi `relabel_configs`.

Langkahnya:

### Langkah 1

```yaml
- source_labels: [__address__]
  target_label: __param_target
```

Mengubah target asli menjadi parameter `target`.

Dari:

```text
__address__ = 192.0.2.10
```

Menjadi:

```text
__param_target = 192.0.2.10
```

Prometheus akan mengubah `__param_target` menjadi query string:

```text
target=192.0.2.10
```

### Langkah 2

```yaml
- source_labels: [__param_target]
  target_label: instance
```

Mengisi label `instance` dengan target asli.

Hasil:

```text
instance="192.0.2.10"
```

Ini berguna agar di Grafana/alert terlihat target asli, bukan alamat Blackbox Exporter.

### Langkah 3

```yaml
- target_label: __address__
  replacement: blackbox-exporter:9115
```

Mengganti alamat scrape menjadi Blackbox Exporter.

Hasil akhirnya:

```text
Prometheus scrape:
http://blackbox-exporter:9115/probe?module=icmp&target=192.0.2.10
```

Metric yang muncul:

```text
probe_success{job="blackbox_icmp", instance="192.0.2.10", host="server01", project="example-project"}
```

## 8. Apa Itu Metric `up`

Prometheus otomatis membuat metric `up` untuk setiap target scrape.

Nilainya:

```text
1 = scrape berhasil
0 = scrape gagal
```

Contoh:

```promql
up{job="prometheus"}
```

Artinya apakah Prometheus berhasil scrape Prometheus sendiri.

```promql
up{job="node"}
```

Artinya apakah Prometheus berhasil scrape Node Exporter di server target.

```promql
up{job="blackbox-exporter"}
```

Artinya apakah Prometheus berhasil scrape Blackbox Exporter.

Untuk Blackbox probe, ada dua konsep yang berbeda:

```promql
up{job="blackbox_icmp"}
```

Artinya Prometheus berhasil scrape endpoint `/probe` di Blackbox Exporter.

Sedangkan:

```promql
probe_success{job="blackbox_icmp"}
```

Artinya hasil ping ICMP ke target berhasil atau tidak.

Jadi untuk uptime host via ping, gunakan:

```promql
probe_success{job="blackbox_icmp"}
```

Bukan:

```promql
up{job="blackbox_icmp"}
```

Karena `up{job="blackbox_icmp"}` hanya membuktikan Blackbox Exporter bisa dihubungi oleh Prometheus.

## 9. Apa Itu Recording Rules

Recording rules adalah aturan untuk membuat metric baru dari query PromQL.

File:

```text
prometheus/rules/recording.yml
```

Contoh:

```yaml
- record: host:up:probe_icmp
  expr: max by (project, host) (probe_success{job="blackbox_icmp"})
```

Artinya:

```text
Prometheus menjalankan query ini berkala:
max by (project, host) (probe_success{job="blackbox_icmp"})
```

Lalu hasilnya disimpan sebagai metric baru bernama:

```text
host:up:probe_icmp
```

Jadi `host:up:probe_icmp` bukan metric asli dari exporter.

Metric itu dibuat oleh Prometheus dari recording rule.

## 10. Kenapa Ada `record: host:up:probe_icmp`

Metric mentah dari Blackbox ICMP adalah:

```promql
probe_success{job="blackbox_icmp"}
```

Contoh hasil mentah:

```text
probe_success{job="blackbox_icmp",instance="192.0.2.10",project="example-project",host="server01",target_address="192.0.2.10"} 1
```

Metric ini masih detail dan membawa banyak label.

Untuk dashboard dan alert host, kita ingin metric yang lebih sederhana:

```text
satu host = satu status up/down
```

Maka dibuat recording rule:

```yaml
- record: host:up:probe_icmp
  expr: max by (project, host) (probe_success{job="blackbox_icmp"})
```

Hasilnya menjadi:

```text
host:up:probe_icmp{project="example-project",host="server01"} 1
```

Label yang dipertahankan hanya:

```text
project
host
```

Label lain seperti `instance` dan `target_address` dibuang agar dashboard lebih bersih.

Kenapa pakai `max by (project, host)`?

Karena jika suatu saat satu host punya lebih dari satu probe, `max` akan mengambil nilai tertinggi.

Untuk status 0/1:

```text
max(1) = 1
max(0) = 0
max(0, 1) = 1
```

Dalam setup saat ini biasanya satu host punya satu ICMP probe, jadi hasilnya sama seperti `probe_success`, tapi labelnya lebih rapi.

## 11. Bagaimana `host:up:probe_icmp` Bisa Muncul

Urutannya:

### 1. Target ditulis di `targets.yml`

```yaml
servers:
  - name: server01
    address: 192.0.2.10
    labels:
      project: example-project
    probes:
      icmp: true
```

### 2. Generator membuat `icmp.json`

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

### 3. Prometheus job `blackbox_icmp` membaca `icmp.json`

```yaml
file_sd_configs:
  - files:
      - /etc/prometheus/targets/icmp.json
```

### 4. Prometheus meminta Blackbox Exporter ping target

```text
http://blackbox-exporter:9115/probe?module=icmp&target=192.0.2.10
```

### 5. Blackbox Exporter mengembalikan metric mentah

```text
probe_success{job="blackbox_icmp",host="server01",project="example-project"} 1
```

### 6. Recording rule menjalankan query

```promql
max by (project, host) (probe_success{job="blackbox_icmp"})
```

### 7. Prometheus menyimpan hasil sebagai metric baru

```text
host:up:probe_icmp{project="example-project",host="server01"} 1
```

Jadi metric tersebut bisa muncul karena dibuat oleh recording rule.

## 12. Penamaan Recording Rule

Nama seperti ini:

```text
host:up:probe_icmp
```

Adalah konvensi umum Prometheus.

Bukan wajib, tapi membantu pembacaan.

Formatnya kira-kira:

```text
level:metric:detail
```

Untuk project ini:

```text
host:up:probe_icmp
```

Bisa dibaca sebagai:

```text
status up/down host berdasarkan probe ICMP
```

Contoh lain:

```text
host:availability_30d:ratio
```

Bisa dibaca sebagai:

```text
availability host selama 30 hari dalam bentuk rasio 0 sampai 1
```

```text
node:cpu_usage:ratio
```

Bisa dibaca sebagai:

```text
CPU usage dari node exporter dalam bentuk rasio 0 sampai 1
```

## 13. Recording Rules Availability dan Downtime

### `host:availability_30d:ratio`

Konfigurasi:

```yaml
- record: host:availability_30d:ratio
  expr: avg_over_time(host:up:probe_icmp[30d])
```

Artinya:

```text
ambil rata-rata nilai host:up:probe_icmp selama 30 hari
```

Karena `host:up:probe_icmp` nilainya 0 atau 1:

```text
1 = up
0 = down
```

Maka rata-ratanya menjadi availability.

Contoh:

```text
selama 30 hari selalu up
avg = 1
availability = 100%
```

```text
selama 30 hari separuh waktu up, separuh waktu down
avg = 0.5
availability = 50%
```

```text
selama 30 hari down selama 1 jam
avg mendekati 0.9986
availability sekitar 99.86%
```

Di Grafana biasanya dikali 100:

```promql
host:availability_30d:ratio * 100
```

### `host:downtime_30d:seconds`

Konfigurasi:

```yaml
- record: host:downtime_30d:seconds
  expr: (1 - avg_over_time(host:up:probe_icmp[30d])) * 30 * 24 * 3600
```

Artinya:

```text
1 - availability = persentase downtime
```

Lalu dikali jumlah detik dalam 30 hari:

```text
30 * 24 * 3600 = 2.592.000 detik
```

Contoh:

```text
availability = 1
1 - 1 = 0
downtime = 0 detik
```

```text
availability = 0.99
1 - 0.99 = 0.01
downtime = 0.01 * 2.592.000 = 25.920 detik = 7,2 jam
```

## 14. Recording Rules Resource Server

### `node:cpu_usage:ratio`

Konfigurasi:

```yaml
- record: node:cpu_usage:ratio
  expr: 1 - avg by (project, host) (rate(node_cpu_seconds_total{job="node",mode="idle"}[5m]))
```

Artinya:

- Node Exporter memberi metric waktu CPU per mode.
- Mode `idle` artinya CPU sedang menganggur.
- Kalau idle 80%, maka usage 20%.

Rumus:

```text
CPU usage = 1 - CPU idle
```

Nilai `0.20` berarti 20%.

### `node:memory_usage:ratio`

Konfigurasi:

```yaml
- record: node:memory_usage:ratio
  expr: 1 - (node_memory_MemAvailable_bytes{job="node"} / node_memory_MemTotal_bytes{job="node"})
```

Artinya:

```text
memory usage = 1 - memory available / memory total
```

Nilai `0.70` berarti RAM terpakai sekitar 70%.

### `node:filesystem_usage:ratio`

Konfigurasi:

```yaml
- record: node:filesystem_usage:ratio
  expr: 1 - (node_filesystem_avail_bytes{...} / node_filesystem_size_bytes{...})
```

Artinya:

```text
disk usage = 1 - disk available / disk total
```

Beberapa filesystem dikecualikan:

```text
tmpfs
fuse.lxcfs
overlay
squashfs
/run.*
/var/lib/docker/.*
```

Tujuannya agar dashboard tidak ramai oleh filesystem sementara/container.

### `node:inode_usage:ratio`

Konfigurasi:

```yaml
- record: node:inode_usage:ratio
  expr: 1 - (node_filesystem_files_free{...} / node_filesystem_files{...})
```

Artinya menghitung pemakaian inode.

Disk bisa penuh bukan hanya karena ukuran file, tapi juga karena jumlah file terlalu banyak.

## 15. Apa Bedanya Recording Rules dan Alert Rules

### Recording Rules

Recording rules membuat metric baru.

Contoh:

```yaml
- record: host:up:probe_icmp
  expr: max by (project, host) (probe_success{job="blackbox_icmp"})
```

Hasilnya bisa dipakai lagi oleh Grafana dan alert.

### Alert Rules

Alert rules membuat alert jika kondisi tertentu terpenuhi.

Contoh:

```yaml
- alert: HostDown
  expr: host:up:probe_icmp == 0
  for: 2m
```

Artinya:

```text
kalau host:up:probe_icmp bernilai 0 selama 2 menit, kirim alert HostDown
```

Jadi:

```text
recording rule = membuat metric baru
alert rule = membuat notifikasi jika metric bermasalah
```

## 16. Kenapa Alert `HostDown` Pakai `host:up:probe_icmp`

Alert:

```yaml
- alert: HostDown
  expr: host:up:probe_icmp == 0
  for: 2m
```

Tidak memakai langsung:

```promql
probe_success{job="blackbox_icmp"} == 0
```

Alasannya:

- `host:up:probe_icmp` labelnya lebih bersih.
- Sudah dibuat per host.
- Query alert lebih mudah dibaca.
- Dashboard dan alert memakai sumber yang sama.

Namun di file alert juga masih ada:

```yaml
- alert: ICMPDown
  expr: probe_success{job="blackbox_icmp"} == 0
```

Ini alert yang lebih dekat ke probe mentah.

Perbedaannya:

| Alert | Metric | Fungsi |
|---|---|---|
| `HostDown` | `host:up:probe_icmp` | status host hasil recording |
| `ICMPDown` | `probe_success{job="blackbox_icmp"}` | status probe ICMP mentah |

Dalam praktik, keduanya bisa terlihat mirip.

Kalau ingin alert lebih sederhana, biasanya cukup salah satu saja. Project ini menyimpan keduanya agar ada level host dan level probe mentah.

## 17. Alert Resource Server

Alert resource memakai recording rules dari Node Exporter.

Contoh:

```yaml
- alert: HighCPUUsage
  expr: node:cpu_usage:ratio > 0.85
  for: 10m
```

Artinya:

```text
CPU usage lebih dari 85% selama 10 menit
```

```yaml
- alert: HighMemoryUsage
  expr: node:memory_usage:ratio{job="node"} > 0.90
  for: 10m
```

Artinya:

```text
RAM usage lebih dari 90% selama 10 menit
```

```yaml
- alert: DiskUsageHigh
  expr: node:filesystem_usage:ratio{job="node"} > 0.85
  for: 10m
```

Artinya:

```text
Disk usage lebih dari 85% selama 10 menit
```

## 18. Alert Service Systemd

Alert:

```yaml
- alert: ServiceDown
  expr: node_systemd_unit_state{job="node",state="active",name=~"(nginx|php.*fpm|mysql|mysqld|mariadb|redis|redis-server|docker|ssh|sshd)\\.service"} == 0
  for: 2m
```

Metric ini berasal dari Node Exporter systemd collector.

Agar metric ini muncul, Node Exporter di target harus dijalankan dengan:

```bash
--collector.systemd
--collector.systemd.unit-include='(nginx|php.*fpm|mysql|mysqld|mariadb|redis|redis-server|docker|ssh|sshd)\.service'
```

Makna query:

```text
ambil service systemd yang state active-nya bernilai 0
```

Kalau service aktif:

```text
node_systemd_unit_state{name="nginx.service",state="active"} 1
```

Kalau service tidak aktif:

```text
node_systemd_unit_state{name="nginx.service",state="active"} 0
```

Maka alert firing.

## 19. Cara Debug Query di Prometheus

Buka Prometheus UI:

```text
/prometheus/
```

Coba query bertahap.

### Cek target scrape

```promql
up
```

### Cek Node Exporter target

```promql
up{job="node"}
```

### Cek ICMP probe mentah

```promql
probe_success{job="blackbox_icmp"}
```

### Cek hasil recording ICMP

```promql
host:up:probe_icmp
```

### Cek availability 30 hari

```promql
host:availability_30d:ratio * 100
```

### Cek resource recording

```promql
node:cpu_usage:ratio * 100
node:memory_usage:ratio * 100
node:filesystem_usage:ratio * 100
```

### Cek service systemd

```promql
node_systemd_unit_state{job="node",state="active"}
```

Kalau query recording rule tidak muncul, cek:

```text
Status → Rules
```

Pastikan group recording rule tidak error.

## 20. Cara Membaca Label

Contoh metric:

```text
host:up:probe_icmp{project="example-project",host="server01"} 1
```

Artinya:

| Bagian | Arti |
|---|---|
| `host:up:probe_icmp` | nama metric |
| `project="example-project"` | project target |
| `host="server01"` | nama host |
| `1` | status up |

Contoh lain:

```text
probe_success{job="blackbox_icmp",instance="192.0.2.10",host="server01"} 1
```

Artinya:

| Bagian | Arti |
|---|---|
| `probe_success` | hasil probe blackbox |
| `job="blackbox_icmp"` | job scrape yang menghasilkan metric |
| `instance="192.0.2.10"` | target yang diprobe |
| `host="server01"` | label host dari `targets.yml` |
| `1` | probe berhasil |

## 21. Checklist Kalau Ada Data `No Data`

### `host:up:probe_icmp` No Data

Cek:

```promql
probe_success{job="blackbox_icmp"}
```

Kalau `probe_success` juga kosong:

- cek `targets.yml`
- regenerate file target
- cek `config/targets/icmp.json`
- cek Prometheus menu Status → Targets

Kalau `probe_success` ada tapi `host:up:probe_icmp` kosong:

- cek `prometheus/rules/recording.yml`
- cek Prometheus menu Status → Rules
- cek apakah rule error

### `node:cpu_usage:ratio` No Data

Cek:

```promql
node_cpu_seconds_total{job="node"}
```

Kalau kosong:

- Node Exporter belum jalan
- port 9100 tidak terbuka
- firewall memblokir
- `node.json` salah

### `node_systemd_unit_state` No Data

Cek Node Exporter sudah memakai flag:

```bash
--collector.systemd
```

Lalu cek metric:

```promql
node_systemd_unit_state{job="node"}
```

Kalau kosong, systemd collector belum aktif atau Node Exporter tidak punya akses ke systemd.

## 22. Command Harian Terkait Config

Regenerate target dari `targets.yml`:

```bash
docker compose run --rm file-sd-generator
```

Render Alertmanager config dari template:

```bash
docker compose run --rm alertmanager-config
```

Reload Prometheus config tanpa restart container:

```bash
curl -X POST http://127.0.0.1:9090/-/reload
```

Cek config Prometheus:

```bash
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
```

Cek rules di Prometheus UI:

```text
/prometheus/rules
```

Cek targets di Prometheus UI:

```text
/prometheus/targets
```

## 23. Ringkasan Super Singkat

```text
job_name prometheus
= Prometheus memonitor dirinya sendiri

job_name blackbox-exporter
= Prometheus memonitor service Blackbox Exporter

job_name blackbox_icmp
= Prometheus meminta Blackbox Exporter ping host target

up{job="node"}
= Prometheus berhasil scrape Node Exporter atau tidak

probe_success{job="blackbox_icmp"}
= hasil ping ICMP ke target berhasil atau tidak

host:up:probe_icmp
= metric baru hasil recording rule dari probe_success blackbox_icmp

recording rule
= query PromQL yang disimpan sebagai metric baru

alert rule
= kondisi PromQL yang menghasilkan alert
```
