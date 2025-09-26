import os
import time
import json
import socket
import requests
import urllib3
import random
from datetime import datetime, timezone

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PUSH_ENDPOINT = os.getenv("PUSH_ENDPOINT", "http://aggregator:8080/metrics")
INTERVAL = int(os.getenv("SCRAPE_INTERVAL", "30"))
JITTER_PERCENT = float(os.getenv("JITTER_PERCENT", "20"))  # +/- 20% jitter by default
MAX_CONSECUTIVE_FAILURES = int(os.getenv("MAX_CONSECUTIVE_FAILURES", "5"))  # Exit after 5 consecutive failures
KUBELET_ENDPOINT = os.getenv("KUBELET_ENDPOINT", "https://127.0.0.1:10250/stats/summary")
ENABLE_EC2_INSTANCE_ID = os.getenv("ENABLE_EC2_INSTANCE_ID", "true").lower() == "true"
EC2_METADATA_ENDPOINT = "http://169.254.169.254/latest/meta-data/instance-id"
EC2_METADATA_TOKEN_TTL = os.getenv("EC2_METADATA_TOKEN_TTL", "21600")  # 6 hours default
FORCE_IMDSV1 = os.getenv("FORCE_IMDSV1", "false").lower() == "true"  # Force IMDSv1 only

# Kubernetes mounts these into every pod
TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

def get_randomized_interval():
    """
    Return a randomized interval with jitter to prevent thundering herd.
    Applies +/- JITTER_PERCENT variance to the base INTERVAL.
    """
    jitter_range = INTERVAL * (JITTER_PERCENT / 100)
    jitter = random.uniform(-jitter_range, jitter_range)
    return max(1, INTERVAL + jitter)  # Ensure minimum 1 second interval

def get_token():
    with open(TOKEN_PATH, "r") as f:
        return f.read().strip()

def get_ec2_instance_id():
    """
    Fetch EC2 instance ID from AWS metadata endpoint using IMDSv2.
    Uses token-based authentication for improved security.
    Falls back to IMDSv1 if IMDSv2 fails, unless FORCE_IMDSV1 is enabled.
    Returns None if the endpoint is not available or times out.
    """
    if not ENABLE_EC2_INSTANCE_ID:
        return None
    
    # If forced to use IMDSv1 only, skip IMDSv2
    if FORCE_IMDSV1:
        print("FORCE_IMDSV1 enabled, using IMDSv1 only")
        try:
            resp = requests.get(
                EC2_METADATA_ENDPOINT,
                timeout=2
            )
            resp.raise_for_status()
            instance_id = resp.text.strip()
            print(f"Retrieved EC2 instance ID (IMDSv1): {instance_id}")
            return instance_id
        except Exception as e:
            print(f"Failed to retrieve EC2 instance ID (IMDSv1): {e}")
            return None
    
    # First try IMDSv2 (token-based)
    try:
        # Step 1: Get session token for IMDSv2
        token_url = "http://169.254.169.254/latest/api/token"
        token_headers = {
            "X-aws-ec2-metadata-token-ttl-seconds": EC2_METADATA_TOKEN_TTL
        }
        
        token_resp = requests.put(
            token_url,
            headers=token_headers,
            timeout=2
        )
        token_resp.raise_for_status()
        session_token = token_resp.text.strip()
        
        # Step 2: Use session token to get instance ID
        metadata_headers = {
            "X-aws-ec2-metadata-token": session_token
        }
        
        resp = requests.get(
            EC2_METADATA_ENDPOINT,
            headers=metadata_headers,
            timeout=2
        )
        resp.raise_for_status()
        instance_id = resp.text.strip()
        print(f"Retrieved EC2 instance ID (IMDSv2): {instance_id}")
        return instance_id
        
    except Exception as e:
        print(f"IMDSv2 failed: {e}, falling back to IMDSv1")
        
        # Fallback to IMDSv1 for backward compatibility
        try:
            resp = requests.get(
                EC2_METADATA_ENDPOINT,
                timeout=2
            )
            resp.raise_for_status()
            instance_id = resp.text.strip()
            print(f"Retrieved EC2 instance ID (IMDSv1 fallback): {instance_id}")
            return instance_id
        except Exception as fallback_e:
            print(f"Failed to retrieve EC2 instance ID (both IMDSv2 and IMDSv1): {fallback_e}")
            return None

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
        return resp.json(), True
    except Exception as e:
        print(f"Error fetching kubelet summary: {e}")
        return None, False

def parse_summary(summary, ec2_instance_id=None):
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

        # Find earliest container start time
        earliest_start_time = None
        for container in pod.get("containers", []):
            start_time_str = container.get("startTime")
            if start_time_str:
                try:
                    start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    if earliest_start_time is None or start_time < earliest_start_time:
                        earliest_start_time = start_time
                except ValueError:
                    # Skip invalid timestamps
                    continue

        pods_data.append({
            "pod_id": pod_id,
            "namespace": namespace,
            "name": name,
            "cpu_usage_cores": cpu_nano / 1e9,
            "memory_usage_bytes": mem_bytes,
            "net_tx_bytes": net_tx,
            "net_rx_bytes": net_rx,
            "pod_start_time": earliest_start_time.isoformat() if earliest_start_time else None
        })

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "node_name": node_name,
        "hostname": socket.gethostname(),
        "pods": pods_data
    }
    
    # Add EC2 instance ID if available
    if ec2_instance_id:
        payload["ec2_instance_id"] = ec2_instance_id
    
    return payload

def push_metrics(payload):
    try:
        headers = {"Content-Type": "application/json"}
        resp = requests.post(PUSH_ENDPOINT, headers=headers, data=json.dumps(payload), verify=False, timeout=5)
        resp.raise_for_status()
        print(f"Pushed {len(payload['pods'])} pod metrics")
        return True
    except Exception as e:
        print(f"Error pushing metrics: {e}")
        return False

def main():
    # Add initial random delay to spread out collector start times
    initial_delay = random.uniform(0, INTERVAL)
    print(f"Starting collector with initial delay of {initial_delay:.2f} seconds")
    print(f"Will exit after {MAX_CONSECUTIVE_FAILURES} consecutive failures")
    print(f"EC2 instance ID collection: {'enabled' if ENABLE_EC2_INSTANCE_ID else 'disabled'}")
    if ENABLE_EC2_INSTANCE_ID:
        print(f"EC2 metadata mode: {'IMDSv1 only' if FORCE_IMDSV1 else 'IMDSv2 with IMDSv1 fallback'}")
        print(f"EC2 metadata token TTL: {EC2_METADATA_TOKEN_TTL} seconds")
    time.sleep(initial_delay)
    
    token = get_token()
    consecutive_failures = 0
    
    # Get EC2 instance ID once at startup (it doesn't change)
    ec2_instance_id = get_ec2_instance_id() if ENABLE_EC2_INSTANCE_ID else None
    
    while True:
        success = False
        
        # Try to fetch kubelet summary
        summary, fetch_success = fetch_kubelet_summary(token)
        if fetch_success and summary:
            # Try to parse and push metrics
            payload = parse_summary(summary, ec2_instance_id)
            if push_metrics(payload):
                success = True
        
        # Track consecutive failures
        if success:
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            print(f"Consecutive failures: {consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}")
            
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print(f"Reached maximum consecutive failures ({MAX_CONSECUTIVE_FAILURES}). Exiting.")
                exit(1)
        
        # Use randomized interval for next iteration
        sleep_time = get_randomized_interval()
        print(f"Sleeping for {sleep_time:.2f} seconds until next collection")
        time.sleep(sleep_time)

if __name__ == "__main__":
    main()
