import argparse
import json
import time
from pathlib import Path

import yaml

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    FileSystemEventHandler = object
    Observer = None

BASE = Path('/app') if Path('/app/targets.yml').exists() else Path.cwd()
INPUT = BASE / 'targets.yml'
OUTPUT = BASE / 'output' if (BASE / 'output').exists() or BASE == Path('/app') else BASE / 'config' / 'targets'


def safe_labels(server):
    labels = dict(server.get('labels') or {})
    labels['host'] = server['name']
    labels['target_address'] = str(server['address'])
    return {str(k): str(v) for k, v in labels.items()}


def write_json(name, data):
    path = OUTPUT / name
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    tmp.replace(path)


def generate():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    config = yaml.safe_load(INPUT.read_text()) or {}
    node = []
    icmp = []
    http = []
    tcp = []
    nginx = []

    for server in config.get('servers', []):
        labels = safe_labels(server)
        address = str(server['address'])
        exporters = server.get('exporters') or {}
        probes = server.get('probes') or {}

        if exporters.get('node'):
            port = exporters.get('node_port', 9100)
            node.append({'targets': [f'{address}:{port}'], 'labels': labels})

        if probes.get('icmp'):
            icmp.append({'targets': [address], 'labels': labels})

        for url in probes.get('http') or []:
            item_labels = dict(labels)
            item_labels['probe_url'] = str(url)
            if str(url).lower().startswith('https://'):
                item_labels['probe_scheme'] = 'https'
            else:
                item_labels['probe_scheme'] = 'http'
            http.append({'targets': [str(url)], 'labels': item_labels})

        for port in probes.get('tcp') or []:
            item_labels = dict(labels)
            item_labels['port'] = str(port)
            tcp.append({'targets': [f'{address}:{port}'], 'labels': item_labels})

        for url in probes.get('nginx_status') or []:
            item_labels = dict(labels)
            item_labels['nginx_monitoring'] = 'stub_status_probe'
            nginx.append({'targets': [str(url)], 'labels': item_labels})

    write_json('node.json', node)
    write_json('icmp.json', icmp)
    write_json('http.json', http)
    write_json('tcp.json', tcp)
    write_json('nginx.json', nginx)


class Handler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path == str(INPUT):
            generate()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    generate()
    if args.watch:
        if Observer is None:
            raise RuntimeError('watchdog package is required for --watch')
        observer = Observer()
        observer.schedule(Handler(), str(INPUT.parent), recursive=False)
        observer.start()
        try:
            while True:
                time.sleep(60)
        finally:
            observer.stop()
            observer.join()


if __name__ == '__main__':
    main()
