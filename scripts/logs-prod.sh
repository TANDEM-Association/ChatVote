#!/usr/bin/env bash
# logs-prod.sh — Unified production log viewer for ChatVote
# Usage: ./scripts/logs-prod.sh [all|backend|frontend|qdrant|k8s] [--lines N] [--since 5m]
#
# Examples:
#   make logs-prod              # All services, last 5 minutes
#   make logs-backend           # Backend only
#   make logs-frontend          # Frontend only
#   make logs-qdrant            # Qdrant K8s pods
#   make logs-prod SINCE=15m    # Last 15 minutes
#   make logs-prod LINES=50     # Last 50 lines per service

set -euo pipefail

# ---------------------------------------------------------------------------
# Config (from .env files)
# ---------------------------------------------------------------------------
BACKEND_ENV="CHATVOTE-BackEnd/.env"
PROD_ENV="CHATVOTE-BackEnd/.env.prod"

LOKI_URL="https://3160ee03-9475-4793-8f22-748cff072a91.logs.cockpit.fr-par.scw.cloud"
LOKI_TOKEN=$(grep -E '^SCALEWAY_COCKPIT_LOGS_TOKEN=' "$BACKEND_ENV" 2>/dev/null | cut -d= -f2 || echo "")
BACKEND_RESOURCE="chatvoteoan3waxf-backend-prod"
VERCEL_DOMAIN="chatvote-frontend"
K8S_NS_PROD="chatvote-prod"

# Defaults
SERVICE="${1:-all}"
LINES="${LINES:-30}"
SINCE="${SINCE:-5m}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

header() {
    echo ""
    echo -e "${BOLD}${1}${NC}"
    echo -e "${DIM}$(printf '─%.0s' {1..60})${NC}"
}

# Convert "5m" / "1h" / "30s" to seconds for date math
since_to_seconds() {
    local val="${1%[smhd]}"
    local unit="${1: -1}"
    case "$unit" in
        s) echo "$val" ;;
        m) echo $((val * 60)) ;;
        h) echo $((val * 3600)) ;;
        d) echo $((val * 86400)) ;;
        *) echo $((val * 60)) ;;  # default to minutes
    esac
}

# ---------------------------------------------------------------------------
# Backend logs (Scaleway Cockpit / Loki)
# ---------------------------------------------------------------------------

logs_backend() {
    header "🔧 Backend — Scaleway Serverless Container"

    if [ -z "$LOKI_TOKEN" ]; then
        echo -e "${RED}  SCALEWAY_COCKPIT_LOGS_TOKEN not found in $BACKEND_ENV${NC}"
        echo "  Set it to query Loki logs."
        return 1
    fi

    local secs
    secs=$(since_to_seconds "$SINCE")
    local start_ns end_ns
    # macOS date
    if date -v-1S +%s >/dev/null 2>&1; then
        start_ns="$(date -v-${secs}S +%s)000000000"
        end_ns="$(date +%s)000000000"
    else
        start_ns="$(date -d "-${secs} seconds" +%s)000000000"
        end_ns="$(date +%s)000000000"
    fi

    local query="{resource_name=\"${BACKEND_RESOURCE}\"}"
    local encoded_query
    encoded_query=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$query'))")

    local response
    response=$(curl -s \
        -H "Authorization: Bearer $LOKI_TOKEN" \
        "$LOKI_URL/loki/api/v1/query_range?query=${encoded_query}&limit=${LINES}&direction=backward&start=${start_ns}&end=${end_ns}" 2>&1)

    if echo "$response" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data.get('status') != 'success':
    print('  Query failed:', data.get('message', 'unknown error'))
    sys.exit(1)
results = data.get('data', {}).get('result', [])
if not results:
    print('  No logs in the last $SINCE')
    sys.exit(0)
lines = []
for stream in results:
    for ts, val in stream.get('values', []):
        try:
            msg = json.loads(val).get('message', val)
        except (json.JSONDecodeError, AttributeError):
            msg = val
        lines.append((int(ts), msg))
lines.sort()
for _, msg in lines[-${LINES}:]:
    print(msg)
" 2>&1; then
        true
    else
        echo -e "${RED}  Failed to parse Loki response${NC}"
    fi
}

# ---------------------------------------------------------------------------
# Frontend logs (Vercel)
# ---------------------------------------------------------------------------

logs_frontend() {
    header "🌐 Frontend — Vercel"

    if ! command -v vercel >/dev/null 2>&1; then
        echo -e "${RED}  vercel CLI not found. Install: bun i -g vercel${NC}"
        return 1
    fi

    # Get latest production deployment URL from vercel ls output
    local deploy_url
    deploy_url=$(vercel ls 2>/dev/null | grep "● Ready" | grep "Production" | head -1 | awk '{print $2}' || echo "")

    if [ -z "$deploy_url" ]; then
        echo -e "${YELLOW}  No recent production deployment found${NC}"
        echo "  Run 'vercel ls' to check."
        return 1
    fi

    echo -e "  ${DIM}Deployment: ${deploy_url}${NC}"
    echo -e "  ${DIM}(Vercel streams live — Ctrl+C to stop, timeout 30s)${NC}"
    echo ""
    timeout 30 vercel logs "$deploy_url" 2>&1 | head -"$LINES" || true
}

# ---------------------------------------------------------------------------
# Qdrant logs (Kubernetes)
# ---------------------------------------------------------------------------

logs_qdrant() {
    header "🧠 Qdrant — Kubernetes (${K8S_NS_PROD})"

    if ! command -v kubectl >/dev/null 2>&1; then
        echo -e "${RED}  kubectl not found${NC}"
        return 1
    fi

    # Check if we can reach the cluster
    if ! kubectl cluster-info >/dev/null 2>&1; then
        echo -e "${RED}  Cannot reach K8s cluster. Check kubectl context.${NC}"
        return 1
    fi

    local secs
    secs=$(since_to_seconds "$SINCE")

    # Get qdrant pods
    local pods
    pods=$(kubectl get pods -n "$K8S_NS_PROD" -l app=qdrant --no-headers -o custom-columns=":metadata.name" 2>/dev/null)

    if [ -z "$pods" ]; then
        # Try without label selector
        pods=$(kubectl get pods -n "$K8S_NS_PROD" --no-headers -o custom-columns=":metadata.name" 2>/dev/null | grep -i qdrant || echo "")
    fi

    if [ -z "$pods" ]; then
        echo -e "${YELLOW}  No Qdrant pods found in namespace ${K8S_NS_PROD}${NC}"
        echo "  Available pods:"
        kubectl get pods -n "$K8S_NS_PROD" --no-headers 2>/dev/null | sed 's/^/    /'
        return 1
    fi

    for pod in $pods; do
        echo -e "  ${CYAN}Pod: ${pod}${NC}"
        kubectl logs -n "$K8S_NS_PROD" "$pod" --since="${secs}s" --tail="$LINES" 2>&1 | sed 's/^/  /'
        echo ""
    done
}

# ---------------------------------------------------------------------------
# K8s overview (all pods in prod namespace)
# ---------------------------------------------------------------------------

logs_k8s() {
    header "☸️  Kubernetes — All pods (${K8S_NS_PROD})"

    echo -e "  ${DIM}Pod status:${NC}"
    kubectl get pods -n "$K8S_NS_PROD" -o wide 2>&1 | sed 's/^/  /'
    echo ""

    echo -e "  ${DIM}Events (last ${SINCE}):${NC}"
    kubectl get events -n "$K8S_NS_PROD" --sort-by='.lastTimestamp' 2>&1 | tail -"$LINES" | sed 's/^/  /'
}

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

check_health() {
    header "💓 Health Check"

    printf "  %-30s" "Backend (Scaleway)..."
    if curl -sf --max-time 5 "https://chatvoteoan3waxf-backend-prod.functions.fnc.fr-par.scw.cloud/healthz" >/dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAIL${NC}"
    fi

    printf "  %-30s" "Frontend (Vercel)..."
    if curl -sf --max-time 5 "https://app.chatvote.org" >/dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAIL${NC}"
    fi

    printf "  %-30s" "Qdrant (K8s LB)..."
    local qdrant_key
    qdrant_key=$(grep -E '^QDRANT_API_KEY=' "$PROD_ENV" 2>/dev/null | cut -d= -f2 || echo "")
    if curl -sf --max-time 5 -H "api-key: ${qdrant_key}" "http://212.47.245.238:6333/healthz" >/dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAIL${NC}"
    fi

    printf "  %-30s" "K8s cluster..."
    if kubectl cluster-info >/dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAIL${NC}"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   ChatVote Production Logs (${SINCE})     ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"

case "$SERVICE" in
    all)
        check_health
        logs_backend
        logs_frontend
        logs_qdrant
        ;;
    backend|be)
        logs_backend
        ;;
    frontend|fe|vercel)
        logs_frontend
        ;;
    qdrant|vector)
        logs_qdrant
        ;;
    k8s|kube|kubernetes)
        logs_k8s
        ;;
    health|check)
        check_health
        ;;
    *)
        echo "Usage: $0 [all|backend|frontend|qdrant|k8s|health] [--lines N] [--since 5m]"
        echo ""
        echo "  all       — All services (default)"
        echo "  backend   — Scaleway Serverless Container (Loki)"
        echo "  frontend  — Vercel deployment logs"
        echo "  qdrant    — Qdrant K8s pod logs"
        echo "  k8s       — All K8s pods + events"
        echo "  health    — Health check only"
        echo ""
        echo "Environment variables:"
        echo "  LINES=30   Number of log lines per service"
        echo "  SINCE=5m   Time window (5m, 1h, 30s, 1d)"
        exit 1
        ;;
esac

echo ""
