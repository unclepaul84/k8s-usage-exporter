import os
import time
import json
import socket
import requests
import urllib3
from datetime import datetime, timezone

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PUSH_ENDPOINT = os.getenv("PUSH_ENDPOINT", "http://aggregator:8080/metrics")
INTERVAL = int(os.getenv("SCRAPE_INTERVAL", "30"))
KUBELET_ENDPOINT = os.getenv("KUBELET_ENDPOINT", "https://127.0.0.1:10250/stats/summary")

# Kubernetes mounts these into every pod
TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

def get_token():
    with open(TOKEN_PATH, "r") as f:
        return f.read().strip()

def fetch_kubelet_summary(token):
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.get(
            KUBELET_ENDPOINT,
            headers=headers,
            verify=False,  # Skip SSL verification
            timeout=5
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching kubelet summary: {e}")
        return None

def parse_summary(summary):
    node_name = summary["node"]["nodeName"]
    pods_data = []

    for pod in summary.get("pods", []):
        pod_id = pod["podRef"]["uid"]
        namespace = pod["podRef"]["namespace"]
        name = pod["podRef"]["name"]

        cpu_nano = int(pod.get("cpu", {}).get("usageNanoCores", 0))
        mem_bytes = int(pod.get("memory", {}).get("usageBytes", 0))
        net_tx = int(pod.get("network", {}).get("txBytes", 0))
        net_rx = int(pod.get("network", {}).get("rxBytes", 0))

        pods_data.append({
            "pod_id": pod_id,
            "namespace": namespace,
            "name": name,
            "cpu_cores_used": cpu_nano / 1e9,
            "mem_gb_used": mem_bytes / (1024**3),
            "net_tx_bytes": net_tx,
            "net_rx_bytes": net_rx
        })

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "node_name": node_name,
        "hostname": socket.gethostname(),
        "pods": pods_data
    }

def push_metrics(payload):
    try:
        print(f"Pushing metrics: {json.dumps(payload)}")
        headers = {"Content-Type": "application/json"}
        resp = requests.post(PUSH_ENDPOINT, headers=headers, data=json.dumps(payload), verify=False, timeout=5)
        resp.raise_for_status()
        print(f"Pushed {len(payload['pods'])} pod metrics")
    except Exception as e:
        print(f"Error pushing metrics: {e}")

def main():
    token = get_token()
    while True:
        summary = fetch_kubelet_summary(token)
        if summary:
            payload = parse_summary(summary)
            push_metrics(payload)
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
