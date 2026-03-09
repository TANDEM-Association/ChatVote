---
name: scaleway-logs
description: Query Scaleway Cockpit (Loki) logs for backend container. Use when debugging backend errors, checking container health, or investigating issues on prod.
---

# Scaleway Cockpit Logs

Query backend container logs via the Scaleway Cockpit Loki API.

## Configuration

Env vars (in `CHATVOTE-BackEnd/.env`):
- `SCALEWAY_COCKPIT_LOGS_TOKEN` — Cockpit API token (Query metrics + Query logs)
- `SCALEWAY_COCKPIT_LOGS_URL` — Loki endpoint: `https://3160ee03-9475-4793-8f22-748cff072a91.logs.cockpit.fr-par.scw.cloud`

## Loki Query Reference

### Base curl command

```bash
LOKI_URL="https://3160ee03-9475-4793-8f22-748cff072a91.logs.cockpit.fr-par.scw.cloud"
TOKEN="$(grep SCALEWAY_COCKPIT_LOGS_TOKEN CHATVOTE-BackEnd/.env | cut -d= -f2)"

curl -sS -G -H "Authorization: Bearer $TOKEN" \
  "$LOKI_URL/loki/api/v1/query_range" \
  --data-urlencode 'query={resource_name="chatvoteoan3waxf-backend-prod"}' \
  --data-urlencode 'limit=50' \
  --data-urlencode "start=$(date -v-1H +%s)000000000" \
  --data-urlencode "end=$(date +%s)000000000"
```

### Common queries

**All errors (last hour):**
```
{resource_name="chatvoteoan3waxf-backend-prod"} |~ "(?i)(error|exception|traceback|failed)"
```

**Specific error keyword:**
```
{resource_name="chatvoteoan3waxf-backend-prod"} |~ "keyword_here"
```

**Qdrant errors:**
```
{resource_name="chatvoteoan3waxf-backend-prod"} |~ "qdrant"
```

**All recent logs (no filter):**
```
{resource_name="chatvoteoan3waxf-backend-prod"}
```

**Qdrant container logs:**
```
{resource_name="chatvoteoan3waxf-qdrant-prod"}
```

### Parsing response

```bash
# Save and parse with python
curl ... > /tmp/loki_logs.json
python3 -c "
import json
with open('/tmp/loki_logs.json') as f:
    data = json.load(f)
for stream in data.get('data',{}).get('result',[]):
    for ts, line in stream.get('values',[]):
        print(line[:300])
        print('---')
"
```

### Time ranges

- Last 1 hour: `start=$(date -v-1H +%s)000000000`
- Last 6 hours: `start=$(date -v-6H +%s)000000000`
- Last 24 hours: `start=$(date -v-24H +%s)000000000`

### Available labels

| Label | Values |
|-------|--------|
| `resource_name` | `chatvoteoan3waxf-backend-prod`, `chatvoteoan3waxf-qdrant-prod` |
| `resource_type` | `container` |
| `region` | `fr-par` |

### Grafana dashboard

Browser URL: `https://78c3d473-15a8-46bf-9c9a-339d618c75b5.dashboard.cockpit.scaleway.com/d/scw-serverless-containers-logs/serverless-containers-logs?orgId=1&var-region=fr-par&var-container_name=chatvoteoan3waxf-backend-prod`

## Scaleway Container Management

```bash
# List containers in namespace
scw container container list namespace-id=52e5afec-2904-4f21-bf95-5e892716f3bc region=fr-par -o json

# Backend container ID: ae3956d0-2a9b-4da6-804e-3d923a88fa9c
# Qdrant container ID: ec9339c9-7dc1-451c-b234-9aeef591d0e5

# Get container details
scw container container get ae3956d0-2a9b-4da6-804e-3d923a88fa9c region=fr-par -o json
```
