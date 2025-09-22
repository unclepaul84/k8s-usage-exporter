from flask import Flask, request, jsonify
from kubernetes import client, config, watch
import threading
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# Caches
pod_cache = {}    # pod_uid → metadata + requests/limits
node_cache = {}   # node_name → ec2_instance_id
pvc_cache = {}    # pvc_uid → {namespace, name, storage_request_bytes, volume_name}
pv_cache = {}     # pv_name → {aws_volume_id, storage_class}

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

def watch_nodes():
    config.load_incluster_config()
    # Disable SSL verification for Kubernetes API
    client.configuration.verify_ssl = False
    v1 = client.CoreV1Api()
    w = watch.Watch()
    for event in w.stream(v1.list_node, timeout_seconds=0):
        node = event['object']
        node_name = node.metadata.name
        provider_id = node.spec.provider_id
        ec2_instance_id = None
        if provider_id and provider_id.startswith("aws:///"):
            ec2_instance_id = provider_id.split("/")[-1]
        node_cache[node_name] = ec2_instance_id

def watch_pods():
    config.load_incluster_config()
    # Disable SSL verification for Kubernetes API
    client.configuration.verify_ssl = False
    v1 = client.CoreV1Api()
    w = watch.Watch()
    for event in w.stream(v1.list_pod_for_all_namespaces, timeout_seconds=0):
        pod = event['object']
        uid = pod.metadata.uid

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
                        "aws_volume_id": pv.get("aws_volume_id")
                    })

        pod_cache[uid] = {
            "namespace": pod.metadata.namespace,
            "labels": pod.metadata.labels or {},
            "annotations": pod.metadata.annotations or {},
            "owner": pod.metadata.owner_references[0].name if pod.metadata.owner_references else None,
            "node": pod.spec.node_name,
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

def watch_pvcs():
    config.load_incluster_config()
    # Disable SSL verification for Kubernetes API
    client.configuration.verify_ssl = False
    v1 = client.CoreV1Api()
    w = watch.Watch()
    for event in w.stream(v1.list_persistent_volume_claim_for_all_namespaces, timeout_seconds=0):
        pvc = event['object']
        pvc_cache[pvc.metadata.uid] = {
            "namespace": pvc.metadata.namespace,
            "name": pvc.metadata.name,
            "storage_request_bytes": parse_quantity(pvc.spec.resources.requests.get("storage", "0")),
            "volume_name": pvc.spec.volume_name
        }

def watch_pvs():
    config.load_incluster_config()
    # Disable SSL verification for Kubernetes API
    client.configuration.verify_ssl = False
    v1 = client.CoreV1Api()
    w = watch.Watch()
    for event in w.stream(v1.list_persistent_volume, timeout_seconds=0):
        pv = event['object']
        vol_id = None
        if pv.spec.aws_elastic_block_store:
            vol_id = pv.spec.aws_elastic_block_store.volume_id
        pv_cache[pv.metadata.name] = {
            "aws_volume_id": vol_id,
            "storage_class": pv.spec.storage_class_name
        }

@app.route("/metrics", methods=["POST"])
def receive_metrics():
    payload = request.get_json(force=True)
    node_name = payload.get("node_name")
    ec2_instance_id = node_cache.get(node_name)

    enriched_pods = []
    for pod in payload.get("pods", []):
        uid = pod["pod_id"]
        meta = pod_cache.get(uid, {})
        enriched_pods.append({
            **pod,
            **meta,
            "ec2_instance_id": ec2_instance_id
        })

    enriched_payload = {
        "timestamp": payload["timestamp"],
        "node_name": node_name,
        "ec2_instance_id": ec2_instance_id,
        "pods": enriched_pods
    }

    # TODO: push to DB or message bus
    print(enriched_payload)
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    threading.Thread(target=watch_nodes, daemon=True).start()
    threading.Thread(target=watch_pods, daemon=True).start()
    threading.Thread(target=watch_pvcs, daemon=True).start()
    threading.Thread(target=watch_pvs, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
