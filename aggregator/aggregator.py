from flask import Flask, request, jsonify
from kubernetes import client, config, watch
import threading
import urllib3
import os
import boto3
import pandas as pd
import logging
import json
from datetime import datetime
from io import BytesIO
from botocore.exceptions import ClientError
from jsonschema import validate, ValidationError
import time

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Debug mode configuration
DEBUG_K8S_API = os.getenv("DEBUG_K8S_API", "false").lower() == "true"

# Configure logging
logging.basicConfig(level=logging.DEBUG if DEBUG_K8S_API else logging.INFO)
logger = logging.getLogger(__name__)

# Configure Kubernetes client logging if debug mode is enabled
if DEBUG_K8S_API:
    # Enable debug logging for urllib3 to see HTTP requests/responses
    logging.getLogger("urllib3").setLevel(logging.DEBUG)
    # Enable debug logging for Kubernetes client
    logging.getLogger("kubernetes").setLevel(logging.DEBUG)
    logger.info("Debug mode enabled: All Kubernetes API responses will be logged")
else:
    # Keep urllib3 quiet in non-debug mode
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("kubernetes").setLevel(logging.WARNING)

# S3 Configuration
S3_BUCKET = os.getenv("S3_BUCKET", "k8s-usage-data")
S3_PREFIX = os.getenv("S3_PREFIX", "k8s-metrics/")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")  # Custom S3 endpoint (e.g., MinIO, LocalStack)

# Load JSON Schema for payload validation
def load_payload_schema():
    """Load the JSON schema from file."""
    schema_path = os.path.join(os.path.dirname(__file__), 'payload_schema.json')
    try:
        with open(schema_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Schema file not found at {schema_path}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in schema file: {e}")
        return None
    except Exception as e:
        logger.error(f"Error loading schema file: {e}")
        return None

# Load schema at startup
PAYLOAD_SCHEMA = load_payload_schema()

# Initialize S3 client
s3_client = None

def validate_payload(payload):
    """
    Validate incoming payload against the expected schema.
    Returns (is_valid, errors) tuple.
    """
    if PAYLOAD_SCHEMA is None:
        return True, ["Schema not loaded, skipping validation"]
    
    try:
        validate(instance=payload, schema=PAYLOAD_SCHEMA)
        return True, []
    except ValidationError as e:
        return False, [str(e)]
    except Exception as e:
        return False, [f"Unexpected validation error: {str(e)}"]

def initialize_s3_client():
    """Initialize S3 client with proper configuration."""
    global s3_client
    #try:
        # Configure S3 client with optional custom endpoint
    s3_config = {
        'region_name': AWS_REGION,
        'verify': False  # Disable SSL verification for custom endpoints
    }
    
    if AWS_ENDPOINT_URL:
        s3_config['endpoint_url'] = AWS_ENDPOINT_URL
        logger.info(f"Using custom S3 endpoint: {AWS_ENDPOINT_URL}")
    
    s3_client = boto3.client('s3', **s3_config)
    
    # Test S3 connection
    s3_client.head_bucket(Bucket=S3_BUCKET)
    
    endpoint_info = f" with endpoint {AWS_ENDPOINT_URL}" if AWS_ENDPOINT_URL else ""
    logger.info(f"S3 client initialized successfully for bucket: {S3_BUCKET}{endpoint_info}")
        
    """ except ClientError as e:
    logger.error(f"Failed to initialize S3 client: {e}")
    s3_client = None
except Exception as e:
    logger.error(f"Unexpected error initializing S3 client: {e}")
    s3_client = None"""

def convert_to_parquet(payload):
    """Convert enriched payload to parquet format."""
    try:
        # Flatten the payload for better parquet structure
        records = []
        
        for pod in payload.get("pods", []):
            # Extract nested data
            requests = pod.get("requests", {})
            limits = pod.get("limits", {})
            labels = pod.get("labels", {})
            annotations = pod.get("annotations", {})
            
            # Create flattened record
            record = {
                "timestamp": payload["timestamp"],
                "cluster_id": payload["cluster_id"],
                "node_name": payload["node_name"],
                "ec2_instance_id": payload["ec2_instance_id"],
                "pod_name": pod.get("pod_name"),
                "pod_id": pod.get("pod_id"),
                "namespace": pod.get("namespace"),
                "owner": pod.get("owner"),
                "node": pod.get("node"),          
                "cpu_usage_cores": pod.get("cpu_usage_cores"),
                "cpu_usage_cum_sec": pod.get("cpu_usage_cum", 0),
                "memory_usage_bytes": pod.get("memory_usage_bytes"),
                "net_tx_bytes": pod.get("net_tx_bytes", 0),
                "net_rx_bytes": pod.get("net_rx_bytes", 0),
                "pod_start_time": pod.get("pod_start_time"),
                "requests_cpu_millicores": requests.get("cpu_millicores", 0),
                "requests_memory_bytes": requests.get("memory_bytes", 0),
                "requests_storage_bytes": requests.get("storage_bytes", 0),
                "limits_cpu_millicores": limits.get("cpu_millicores", 0),
                "limits_memory_bytes": limits.get("memory_bytes", 0),
                "limits_storage_bytes": limits.get("storage_bytes", 0),
                # Convert labels and annotations to arrays of strings for parquet compatibility
                "labels": [f"{k}={v}" for k, v in labels.items()] if labels else [],
                "annotations": [f"{k}={v}" for k, v in annotations.items()] if annotations else []
            }
            
            # Add PVC information if available
            pvcs = pod.get("pvcs", [])
            if pvcs:
                record["pvc_count"] = len(pvcs)
                record["total_pvc_storage_bytes"] = sum(pvc.get("storage_request_bytes", 0) for pvc in pvcs)
                record["pvc_names"] = [pvc.get("pvc_name", "") for pvc in pvcs if pvc.get("pvc_name")]
                record["aws_volume_ids"] = [pvc.get("aws_volume_id", "") for pvc in pvcs if pvc.get("aws_volume_id")]
            else:
                record["pvc_count"] = 0
                record["total_pvc_storage_bytes"] = 0
                record["pvc_names"] = []
                record["aws_volume_ids"] = []
                
            records.append(record)
        
        # Convert to DataFrame
        df = pd.DataFrame(records)
        
        # Convert to parquet bytes
        parquet_buffer = BytesIO()
        df.to_parquet(parquet_buffer, index=False, engine='pyarrow')
        parquet_buffer.seek(0)
        
        return parquet_buffer.getvalue()
        
    except Exception as e:
        logger.error(f"Failed to convert payload to parquet: {e}")
        return None

def upload_to_s3(parquet_data, cluster_id, node_name):
    """Upload parquet data to S3 with proper prefix."""
    if not s3_client or not parquet_data:
        logger.warning("S3 client not available or no data to upload")
        return False
        
    try:
        # Generate S3 key with cluster name and date
        current_date = datetime.utcnow().strftime("%Y-%m-%d")
        current_timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        
        # Format the prefix
        formatted_prefix = S3_PREFIX.format(
            cluster_name=cluster_id,
            date=current_date,
            node_name=node_name
        )
        
        # Create the full S3 key
        s3_key = f"{formatted_prefix}cluster-name={cluster_id}/year={datetime.utcnow().strftime('%Y')}/month={datetime.utcnow().strftime('%m')}/day={datetime.utcnow().strftime('%d')}/metrics_{cluster_id}_{node_name}_{current_timestamp}.parquet"
        
        # Upload to S3
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=parquet_data,
            ContentType='application/octet-stream'
        )
        
        logger.info(f"Successfully uploaded metrics to S3: s3://{S3_BUCKET}/{s3_key}")
        return True
        
    except ClientError as e:
        logger.error(f"Failed to upload to S3: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error uploading to S3: {e}")
        return False

# Caches
pod_cache = {}    # pod_uid → metadata + requests/limits
node_cache = {}   # node_name → {ec2_instance_id, cluster_name}
pvc_cache = {}    # pvc_uid → {namespace, name, storage_request_bytes, volume_name}
pv_cache = {}     # pv_name → {aws_volume_id, storage_class}

# Initialization flags for watch threads
watch_initialized = {
    "nodes": False,
    "pods": False,
    "pvcs": False,
    "pvs": False
}

def parse_quantity(qty: str) -> int:
    """Convert K8s quantity string to int (bytes or millicores)."""
    if not qty:
        return 0
    q = qty.lower()
    if q.endswith("m"):
        return int(q[:-1])
    if q.endswith("ki"):
        return int(q[:-2]) * 1024
    if q.endswith("mi"):
        return int(q[:-2]) * 1024 * 1024
    if q.endswith("gi"):
        return int(q[:-2]) * 1024 * 1024 * 1024
    return int(q)

def log_k8s_api_response(operation, obj_type, obj_name, event_type=None, full_object=None):
    """Log Kubernetes API response details when debug mode is enabled."""
    if not DEBUG_K8S_API:
        return
        
    log_msg = f"K8S API [{operation}] {obj_type}: {obj_name}"
    if event_type:
        log_msg += f" (event: {event_type})"
    
    logger.debug(log_msg)
    
    if full_object and DEBUG_K8S_API:
        # Log the full object details in pretty format
        try:
            # Convert to dict if it's a Kubernetes object
            if hasattr(full_object, 'to_dict'):
                obj_dict = full_object.to_dict()
            else:
                obj_dict = full_object
            
            logger.debug(f"Full {obj_type} object data: {json.dumps(obj_dict, indent=2, default=str)}")
        except Exception as e:
            logger.debug(f"Could not serialize {obj_type} object: {e}")

def are_watchers_initialized():
    """Check if all watch threads have been initialized."""
    return all(watch_initialized.values())

def watch_nodes():
    config.load_incluster_config()
    # Disable SSL verification for Kubernetes API
    client.configuration.verify_ssl = False
    v1 = client.CoreV1Api()
    w = watch.Watch()
    
    logger.info("Starting node watcher...")
    
    for event in w.stream(v1.list_node, timeout_seconds=0):
        node = event['object']
        event_type = event['type']
        node_name = node.metadata.name
        provider_id = node.spec.provider_id
        annotations = node.metadata.annotations or {}
        
        # Log API response in debug mode
        log_k8s_api_response("WATCH", "Node", node_name, event_type, node if DEBUG_K8S_API else None)
        
        # Extract EC2 instance ID from provider ID
        ec2_instance_id = None
        if provider_id and provider_id.startswith("aws:///"):
            ec2_instance_id = provider_id.split("/")[-1]
            
        # Extract cluster name from annotation
        cluster_name = annotations.get("cluster.x-k8s.io/cluster-name")
        
        node_cache[node_name] = {
            "ec2_instance_id": ec2_instance_id,
            "cluster_name": cluster_name
        }
        
        if DEBUG_K8S_API:
            logger.debug(f"Node cache updated for {node_name}: {node_cache[node_name]}")
        
        # Mark nodes watcher as initialized after first event
        if not watch_initialized["nodes"]:
            watch_initialized["nodes"] = True
            logger.info("Node watcher initialized")

def watch_pods():
    config.load_incluster_config()
    # Disable SSL verification for Kubernetes API
    client.configuration.verify_ssl = False
    v1 = client.CoreV1Api()
    w = watch.Watch()
    
    logger.info("Starting pod watcher...")
    
    for event in w.stream(v1.list_pod_for_all_namespaces, timeout_seconds=0):
        pod = event['object']
        event_type = event['type']
        uid = pod.metadata.uid
        pod_name = f"{pod.metadata.namespace}/{pod.metadata.name}"

        # Log API response in debug mode
        log_k8s_api_response("WATCH", "Pod", pod_name, event_type, pod if DEBUG_K8S_API else None)

        requests_cpu = requests_mem = requests_storage = 0
        limits_cpu = limits_mem = limits_storage = 0

        for c in pod.spec.containers:
            req = c.resources.requests or {}
            lim = c.resources.limits or {}
            # Requests
            requests_cpu += parse_quantity(req.get("cpu", "0")) if "cpu" in req and req["cpu"].endswith("m") else parse_quantity(req.get("cpu", "0"))*1000
            requests_mem += parse_quantity(req.get("memory", "0"))
            requests_storage += parse_quantity(req.get("ephemeral-storage", "0"))
            # Limits
            limits_cpu += parse_quantity(lim.get("cpu", "0")) if "cpu" in lim and lim["cpu"].endswith("m") else parse_quantity(lim.get("cpu", "0"))*1000
            limits_mem += parse_quantity(lim.get("memory", "0"))
            limits_storage += parse_quantity(lim.get("ephemeral-storage", "0"))

        # Map PVCs mounted by pod
        pvc_info = []
        for vol in pod.spec.volumes or []:
            if vol.persistent_volume_claim:
                claim_name = vol.persistent_volume_claim.claim_name
                ns = pod.metadata.namespace
                # Lookup PVC UID
                pvc = next((v for v in pvc_cache.values() if v["namespace"]==ns and v["name"]==claim_name), None)
                if pvc:
                    pv = pv_cache.get(pvc["volume_name"], {})
                    pvc_info.append({
                        "pvc_name": claim_name,
                        "storage_request_bytes": pvc["storage_request_bytes"],
                        "volume_name": pvc["volume_name"],
                        "aws_volume_id": pv["aws_volume_id"] if pv else None,
                        "storage_class": pv["storage_class"] if pv else None
                    })

        pod_cache[uid] = {
            "namespace": pod.metadata.namespace,
            "labels": pod.metadata.labels or {},
            "annotations": pod.metadata.annotations or {},
            "owner": pod.metadata.owner_references[0].name if pod.metadata.owner_references else None,
            "node": pod.spec.node_name,
            "pod_name": pod.metadata.name,
            "requests": {
                "cpu_millicores": requests_cpu,
                "memory_bytes": requests_mem,
                "storage_bytes": requests_storage,
            },
            "limits": {
                "cpu_millicores": limits_cpu,
                "memory_bytes": limits_mem,
                "storage_bytes": limits_storage,
            },
            "pvcs": pvc_info
        }
        
        if DEBUG_K8S_API:
            logger.debug(f"Pod cache updated for {pod_name}: {json.dumps(pod_cache[uid], indent=2, default=str)}")
        
        # Mark pods watcher as initialized after first event
        if not watch_initialized["pods"]:
            watch_initialized["pods"] = True
            logger.info("Pod watcher initialized")

def watch_pvcs():
    config.load_incluster_config()
    # Disable SSL verification for Kubernetes API
    client.configuration.verify_ssl = False
    
    logger.info("Starting PVC watcher...")
    
    # Mark PVCs watcher as initialized immediately
    if not watch_initialized["pvcs"]:
        watch_initialized["pvcs"] = True
        logger.info("PVC watcher initialized")

    v1 = client.CoreV1Api()
    w = watch.Watch()
    
    for event in w.stream(v1.list_persistent_volume_claim_for_all_namespaces, timeout_seconds=0):
        pvc = event['object']
        event_type = event['type']
        pvc_name = f"{pvc.metadata.namespace}/{pvc.metadata.name}"
        
        # Log API response in debug mode
        log_k8s_api_response("WATCH", "PVC", pvc_name, event_type, pvc if DEBUG_K8S_API else None)
        
        pvc_cache[pvc.metadata.uid] = {
            "namespace": pvc.metadata.namespace,
            "name": pvc.metadata.name,
            "storage_request_bytes": parse_quantity(pvc.spec.resources.requests.get("storage", "0")),
            "volume_name": pvc.spec.volume_name
          
        }
        
        if DEBUG_K8S_API:
            logger.debug(f"PVC cache updated for {pvc_name}: {pvc_cache[pvc.metadata.uid]}")
        
        # Mark PVCs watcher as initialized after first event
   

def watch_pvs():
    config.load_incluster_config()
    # Disable SSL verification for Kubernetes API
    client.configuration.verify_ssl = False
    
    logger.info("Starting PV watcher...")
    
    # Mark PVs watcher as initialized immediately
    if not watch_initialized["pvs"]:
        watch_initialized["pvs"] = True
        logger.info("PV watcher initialized")
        
    v1 = client.CoreV1Api()
    w = watch.Watch()
    
    for event in w.stream(v1.list_persistent_volume, timeout_seconds=0):
        pv = event['object']
        event_type = event['type']
        pv_name = pv.metadata.name
        
        # Log API response in debug mode
        log_k8s_api_response("WATCH", "PV", pv_name, event_type, pv if DEBUG_K8S_API else None)
        
        vol_id = None
        if pv.spec.csi and pv.spec.csi.volume_handle:
            vol_id = pv.spec.csi.volume_handle

        pv_cache[pv.metadata.name] = {
            "aws_volume_id": vol_id,
            "storage_class": pv.spec.storage_class_name if pv.spec else None
        }
        # Mark PVs watcher as initialized after first event
        if DEBUG_K8S_API:
            logger.debug(f"PV cache updated for {pv_name}: {pv_cache[pv.metadata.name]}")
        


def start_background_watchers():
    """Start all Kubernetes watchers as background threads."""
    threading.Thread(target=watch_nodes, daemon=True).start()
    threading.Thread(target=watch_pods, daemon=True).start()
    threading.Thread(target=watch_pvcs, daemon=True).start()
    threading.Thread(target=watch_pvs, daemon=True).start()

def create_app():
    
    # Initialize S3 client
    initialize_s3_client()
    
    # Start background watchers when app is created
    start_background_watchers()
    
    while not are_watchers_initialized():
        logger.info(f"Watchers status: {watch_initialized}")
        time.sleep(2)  # Wait 2 seconds before checking again
        
        logger.info("All watchers initialized successfully!")
        
    """Create and configure the Flask app."""
    app = Flask(__name__)
    

    @app.route("/metrics", methods=["POST"])
    def receive_metrics():
        payload = request.get_json(force=True)
        
        # Validate payload schema
        is_valid, validation_errors = validate_payload(payload)
        if not is_valid:
            logger.warning(f"Payload schema validation failed: {validation_errors}")
            logger.warning(f"Invalid payload structure from {request.remote_addr}")
            # Continue processing despite validation errors (non-blocking)
        else:
            logger.debug("Payload schema validation passed")
        
        # Check if watch threads have been initialized
        if not are_watchers_initialized():
            logger.warning(f"Watch threads not fully initialized yet. Skipping S3 upload. Status: {watch_initialized}")
            return jsonify({"status": "accepted", "message": "watchers not initialized, data not persisted"}), 202
        
        node_name = payload.get("node_name")
        
        # Get node information from cache
        node_info = node_cache.get(node_name, {})
        
        # Use EC2 instance ID from collector payload, fallback to node cache
        ec2_instance_id = payload.get("ec2_instance_id") or node_info.get("ec2_instance_id")
        
        # Use cluster name from node annotation, fallback to environment variable
        cluster_id = node_info.get("cluster_name") or os.getenv("CLUSTER_NAME", "unknown")
        if( cluster_id == "unknown" ):
            logger.warning(f"Cluster name not found in node annotations or environment variable. Please configure CLUSTER_NAME env var.")
        
        enriched_pods = []
        for pod in payload.get("pods", []):
            uid = pod["pod_id"]
            meta = pod_cache.get(uid, {})
            
            # Refresh PVC info from current caches using existing PVC names from pod cache
            if meta and "pvcs" in meta:
                refreshed_pvc_info = []
                for existing_pvc in meta["pvcs"]:
                    pvc_name = existing_pvc.get("pvc_name")
                    namespace = meta.get("namespace")
                    
                    if pvc_name and namespace:
                        # Direct lookup by namespace and name instead of iterating
                        pvc_data = next((v for k, v in pvc_cache.items() 
                                       if v["namespace"] == namespace and v["name"] == pvc_name), None)
                        
                        if pvc_data:
                            pv_data = pv_cache.get(pvc_data.get("volume_name"), {})
                            refreshed_pvc_info.append({
                                "pvc_name": pvc_name,
                                "storage_request_bytes": pvc_data["storage_request_bytes"],
                                "volume_name": pvc_data.get("volume_name"),
                                "aws_volume_id": pv_data.get("aws_volume_id"),
                                "storage_class": pv_data.get("storage_class")
                            })
                        else:
                            # Keep existing data if PVC not found in cache
                            refreshed_pvc_info.append(existing_pvc)
                
                # Update meta with refreshed PVC info
                meta = {**meta, "pvcs": refreshed_pvc_info}
            
            enriched_pods.append({
                **pod,
                **meta,
                "ec2_instance_id": ec2_instance_id
            })

        enriched_payload = {
            "timestamp": payload["timestamp"],
            "cluster_id": cluster_id,
            "node_name": node_name,
            "ec2_instance_id": ec2_instance_id,
            "pods": enriched_pods
        }

        # Convert to parquet and upload to S3
        parquet_data = convert_to_parquet(enriched_payload)
        if parquet_data:
            upload_success = upload_to_s3(parquet_data, cluster_id,node_name)
            if upload_success:
                logger.info(f"Successfully processed and uploaded metrics for cluster {cluster_id}")
            else:
                logger.warning(f"Failed to upload metrics to S3 for cluster {cluster_id}")
        else:
            logger.error(f"Failed to convert metrics to parquet for cluster {cluster_id}")
        
        # Also log for debugging
        logger.debug(f"Processed metrics payload: {enriched_payload}")
        return jsonify({"status": "ok"}), 200

    @app.route("/health", methods=["GET"])
    def health_check():
        """Health check endpoint that includes watcher initialization status."""
        return jsonify({
            "status": "healthy",
            "debug_k8s_api": DEBUG_K8S_API,
            "watchers_initialized": watch_initialized,
            "all_watchers_ready": are_watchers_initialized()
        }), 200
    
    return app




# WSGI application entry point
app = create_app()

if __name__ == "__main__":
    # For standalone execution (development/testing)
    app = create_app()
    app.run(host="0.0.0.0", port=8888)


