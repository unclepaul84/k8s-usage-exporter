import os
import time
import json
import socket
import requests
import urllib3
import random
import logging
from datetime import datetime, timezone

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Debug mode configuration
DEBUG_K8S_API = os.getenv("DEBUG_K8S_API", "false").lower() == "true"

# Configure logging
logging.basicConfig(level=logging.DEBUG if DEBUG_K8S_API else logging.INFO)
logger = logging.getLogger(__name__)

# Configure HTTP client logging if debug mode is enabled
if DEBUG_K8S_API:
    # Enable debug logging for urllib3 to see HTTP requests/responses
    logging.getLogger("urllib3").setLevel(logging.DEBUG)
    # Enable debug logging for requests
    logging.getLogger("requests").setLevel(logging.DEBUG)
    logger.info("Debug mode enabled: All HTTP responses will be logged")
else:
    # Keep urllib3 and requests quiet in non-debug mode
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

PUSH_ENDPOINT = os.getenv("PUSH_ENDPOINT", "http://aggregator:8080/metrics")
INTERVAL = int(os.getenv("SCRAPE_INTERVAL", "30"))
JITTER_PERCENT = float(os.getenv("JITTER_PERCENT", "20"))  # +/- 20% jitter by default
MAX_CONSECUTIVE_FAILURES = int(os.getenv("MAX_CONSECUTIVE_FAILURES", "5"))  # Exit after 5 consecutive failures
KUBELET_ENDPOINT = os.getenv("KUBELET_ENDPOINT", "https://127.0.0.1:10250/stats/summary")
ENABLE_EC2_INSTANCE_ID = os.getenv("ENABLE_EC2_INSTANCE_ID", "true").lower() == "true"
EC2_METADATA_ENDPOINT = "http://169.254.169.254/latest/meta-data/instance-id"
EC2_METADATA_TOKEN_TTL = os.getenv("EC2_METADATA_TOKEN_TTL", "21600")  # 6 hours default
FORCE_IMDSV1 = os.getenv("FORCE_IMDSV1", "false").lower() == "true"  # Force IMDSv1 only

def log_http_response(operation, url, response=None, error=None, request_data=None):
    """Log HTTP response details when debug mode is enabled."""
    if not DEBUG_K8S_API:
        return
        
    log_msg = f"HTTP [{operation}] {url}"
    
    if response:
        log_msg += f" -> {response.status_code} {response.reason}"
        logger.debug(log_msg)
        
        # Log response headers
        if response.headers:
            logger.debug(f"Response headers: {dict(response.headers)}")
            
        # Log response content for certain endpoints (be careful with size)
        content_type = response.headers.get('content-type', '')
        if 'json' in content_type.lower():
            try:
                if hasattr(response, 'json') and callable(response.json):
                    # For successful responses, log a summary instead of full content
                    if response.status_code == 200:
                        try:
                            json_data = response.json()
                            if isinstance(json_data, dict):
                                summary = {k: f"<{type(v).__name__}({len(v) if hasattr(v, '__len__') else 'object'})>" 
                                         for k, v in json_data.items()}
                                logger.debug(f"Response JSON structure: {json.dumps(summary, indent=2)}")
                            else:
                                logger.debug(f"Response JSON type: {type(json_data).__name__}")
                        except:
                            logger.debug(f"Response content length: {len(response.text)} chars")
                    else:
                        # Log error responses in full
                        logger.debug(f"Response JSON: {response.text}")
            except Exception as e:
                logger.debug(f"Could not parse JSON response: {e}")
        else:
            # Log non-JSON responses with length info
            logger.debug(f"Response content (length: {len(response.text)}): {response.text[:500]}{'...' if len(response.text) > 500 else ''}")
    elif error:
        logger.debug(f"{log_msg} -> ERROR: {error}")
        
    # Log request data if provided
    if request_data and DEBUG_K8S_API:
        if isinstance(request_data, dict):
            logger.debug(f"Request data: {json.dumps(request_data, indent=2, default=str)}")
        else:
            logger.debug(f"Request data: {request_data}")

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
        logger.info("FORCE_IMDSV1 enabled, using IMDSv1 only")
        try:
            resp = requests.get(
                EC2_METADATA_ENDPOINT,
                timeout=2
            )
            log_http_response("GET", EC2_METADATA_ENDPOINT, resp)
            resp.raise_for_status()
            instance_id = resp.text.strip()
            logger.info(f"Retrieved EC2 instance ID (IMDSv1): {instance_id}")
            return instance_id
        except Exception as e:
            log_http_response("GET", EC2_METADATA_ENDPOINT, error=e)
            logger.error(f"Failed to retrieve EC2 instance ID (IMDSv1): {e}")
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
        log_http_response("PUT", token_url, token_resp)
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
        log_http_response("GET", EC2_METADATA_ENDPOINT, resp)
        resp.raise_for_status()
        instance_id = resp.text.strip()
        logger.info(f"Retrieved EC2 instance ID (IMDSv2): {instance_id}")
        return instance_id
        
    except Exception as e:
        log_http_response("IMDSv2", "token/metadata", error=e)
        logger.warning(f"IMDSv2 failed: {e}, falling back to IMDSv1")
        
        # Fallback to IMDSv1 for backward compatibility
        try:
            resp = requests.get(
                EC2_METADATA_ENDPOINT,
                timeout=2
            )
            log_http_response("GET", EC2_METADATA_ENDPOINT, resp)
            resp.raise_for_status()
            instance_id = resp.text.strip()
            logger.info(f"Retrieved EC2 instance ID (IMDSv1 fallback): {instance_id}")
            return instance_id
        except Exception as fallback_e:
            log_http_response("GET", EC2_METADATA_ENDPOINT, error=fallback_e)
            logger.error(f"Failed to retrieve EC2 instance ID (both IMDSv2 and IMDSv1): {fallback_e}")
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
        log_http_response("GET", KUBELET_ENDPOINT, resp)
        resp.raise_for_status()
        
        json_data = resp.json()
        if DEBUG_K8S_API:
            # Log summary of kubelet response structure
            if isinstance(json_data, dict):
                summary_info = {
                    "node_name": json_data.get("node", {}).get("nodeName", "unknown"),
                    "pod_count": len(json_data.get("pods", [])),
                    "node_cpu_usage": json_data.get("node", {}).get("cpu", {}).get("usageNanoCores", 0),
                    "node_memory_usage": json_data.get("node", {}).get("memory", {}).get("usageBytes", 0)
                }
                logger.debug(f"Kubelet response summary: {json.dumps(summary_info, indent=2)}")
                
                # Log detailed pod information
                for i, pod in enumerate(json_data.get("pods", [])[:5]):  # Log first 5 pods in detail
                    pod_info = {
                        "pod_name": f"{pod.get('podRef', {}).get('namespace', 'unknown')}/{pod.get('podRef', {}).get('name', 'unknown')}",
                        "cpu_usage": pod.get("cpu", {}).get("usageNanoCores", 0),
                        "memory_usage": pod.get("memory", {}).get("usageBytes", 0)
                    }
                    logger.debug(f"Pod {i+1} details: {json.dumps(pod_info, indent=2)}")
                
                if len(json_data.get("pods", [])) > 5:
                    logger.debug(f"... and {len(json_data.get('pods', [])) - 5} more pods")
        
        return json_data, True
    except Exception as e:
        log_http_response("GET", KUBELET_ENDPOINT, error=e)
        logger.error(f"Error fetching kubelet summary: {e}")
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
        json_payload = json.dumps(payload)
        
        resp = requests.post(
            PUSH_ENDPOINT, 
            headers=headers, 
            data=json_payload, 
            verify=False, 
            timeout=5
        )
        
        # Log the request and response
        log_http_response("POST", PUSH_ENDPOINT, resp, request_data=payload if DEBUG_K8S_API else None)
        
        resp.raise_for_status()
        logger.info(f"Pushed {len(payload['pods'])} pod metrics")
        return True
    except Exception as e:
        log_http_response("POST", PUSH_ENDPOINT, error=e)
        logger.error(f"Error pushing metrics: {e}")
        return False

def main():
    # Add initial random delay to spread out collector start times
    initial_delay = random.uniform(0, INTERVAL)
    logger.info(f"Starting collector with initial delay of {initial_delay:.2f} seconds")
    logger.info(f"Will exit after {MAX_CONSECUTIVE_FAILURES} consecutive failures")
    logger.info(f"EC2 instance ID collection: {'enabled' if ENABLE_EC2_INSTANCE_ID else 'disabled'}")
    logger.info(f"Debug K8S API logging: {'enabled' if DEBUG_K8S_API else 'disabled'}")
    
    if ENABLE_EC2_INSTANCE_ID:
        logger.info(f"EC2 metadata mode: {'IMDSv1 only' if FORCE_IMDSV1 else 'IMDSv2 with IMDSv1 fallback'}")
        logger.info(f"EC2 metadata token TTL: {EC2_METADATA_TOKEN_TTL} seconds")
        
    if DEBUG_K8S_API:
        logger.info(f"Kubelet endpoint: {KUBELET_ENDPOINT}")
        logger.info(f"Push endpoint: {PUSH_ENDPOINT}")
        logger.info(f"Scrape interval: {INTERVAL} seconds (+/- {JITTER_PERCENT}% jitter)")
        
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
            if DEBUG_K8S_API:
                logger.debug(f"Parsed payload summary: {{\"node\": \"{payload.get('node_name')}\", \"pods\": {len(payload.get('pods', []))}, \"timestamp\": \"{payload.get('timestamp')}\"}}") 
            if push_metrics(payload):
                success = True
        
        # Track consecutive failures
        if success:
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            logger.warning(f"Consecutive failures: {consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}")
            
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                logger.error(f"Reached maximum consecutive failures ({MAX_CONSECUTIVE_FAILURES}). Exiting.")
                exit(1)
        
        # Use randomized interval for next iteration
        sleep_time = get_randomized_interval()
        logger.info(f"Sleeping for {sleep_time:.2f} seconds until next collection")
        time.sleep(sleep_time)

if __name__ == "__main__":
    main()
