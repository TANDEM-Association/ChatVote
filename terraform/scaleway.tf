# ──────────────────────────────────────────────
# VPC Private Network
# ──────────────────────────────────────────────

resource "scaleway_vpc_private_network" "main" {
  name   = "chatvote-vpc"
  region = var.region
}

# ──────────────────────────────────────────────
# Kapsule K8s Cluster
# ──────────────────────────────────────────────

resource "scaleway_k8s_cluster" "main" {
  name    = "k8s-ingestion"
  version = var.k8s_version
  cni     = "cilium"

  description        = "Ingestion workloads"
  private_network_id = scaleway_vpc_private_network.main.id

  delete_additional_resources = false

  auto_upgrade {
    enable                        = false
    maintenance_window_start_hour = 0
    maintenance_window_day        = "any"
  }

  autoscaler_config {
    disable_scale_down               = false
    scale_down_delay_after_add       = "10m"
    scale_down_unneeded_time         = "10m"
    scale_down_utilization_threshold = 0.5
    estimator                        = "binpacking"
    expander                         = "random"
    max_graceful_termination_sec     = 600
  }
}

# ──────────────────────────────────────────────
# Node Pools
# ──────────────────────────────────────────────

resource "scaleway_k8s_pool" "main" {
  cluster_id = scaleway_k8s_cluster.main.id
  name       = "pool-par-2-8gb"
  node_type  = "DEV1-L" # 4 vCPU, 8GB RAM
  size       = 1

  autoscaling = true
  min_size    = 1
  max_size    = 2
  autohealing = true

  container_runtime      = "containerd"
  root_volume_type       = "l_ssd"
  root_volume_size_in_gb = 80

  upgrade_policy {
    max_unavailable = 1
    max_surge       = 0
  }
}

resource "scaleway_k8s_pool" "pipeline" {
  cluster_id = scaleway_k8s_cluster.main.id
  name       = "pool-pipeline"
  node_type  = "POP2-2C-8G" # 2 vCPU, 8GB RAM

  size        = 0
  autoscaling = true
  min_size    = 0
  max_size    = 2
  autohealing = true

  container_runtime      = "containerd"
  root_volume_type       = "sbs_5k"
  root_volume_size_in_gb = 40

  upgrade_policy {
    max_unavailable = 1
    max_surge       = 0
  }
}

# ──────────────────────────────────────────────
# Container Registry
# ──────────────────────────────────────────────

resource "scaleway_registry_namespace" "main" {
  name        = "chatvote"
  description = "ChatVote Docker images"
  is_public   = false
}

# ──────────────────────────────────────────────
# Object Storage — Qdrant Snapshots
# ──────────────────────────────────────────────

resource "scaleway_object_bucket" "qdrant_snapshots" {
  name = "chatvote-qdrant-snapshots"

  lifecycle_rule {
    enabled = true
    expiration {
      days = 30
    }
  }
}

# ──────────────────────────────────────────────
# Object Storage — Public PDF Assets
# ──────────────────────────────────────────────
# Replaces Firebase Storage (chat-vote-dev bucket) for
# professions de foi and candidate manifestos.
# Public read — these are official election documents.

resource "scaleway_object_bucket" "public_assets" {
  name = "chatvote-public-assets"
}

resource "scaleway_object_bucket_acl" "public_assets_acl" {
  bucket = scaleway_object_bucket.public_assets.name
  acl    = "public-read"
}

# ──────────────────────────────────────────────
# Object Storage — Langfuse Blob Storage
# ──────────────────────────────────────────────
# Used by production Langfuse v2 for trace event and media storage.
# Private bucket — accessed via S3 API from the K8s Langfuse pod.

resource "scaleway_object_bucket" "langfuse_blobs" {
  name = "chatvote-langfuse-blobs"

  lifecycle_rule {
    enabled = true
    expiration {
      days = 90
    }
  }
}

# ──────────────────────────────────────────────
# Managed Database — Langfuse Postgres
# ──────────────────────────────────────────────
# Replaces the pod-based Postgres StatefulSet in k8s/prod/langfuse/.
# Scaleway Managed Database handles backups, HA, and patching.

resource "scaleway_rdb_instance" "langfuse" {
  name           = "langfuse-db"
  node_type      = "DB-DEV-S" # 1 vCPU, 2GB RAM — sufficient for Langfuse v2
  engine         = "PostgreSQL-15"
  is_ha_cluster  = false
  disable_backup = false

  volume_type       = "lssd"
  volume_size_in_gb = 10

  private_network {
    pn_id = scaleway_vpc_private_network.main.id
  }
}

resource "scaleway_rdb_database" "langfuse" {
  instance_id = scaleway_rdb_instance.langfuse.id
  name        = "langfuse"
}

resource "scaleway_rdb_user" "langfuse" {
  instance_id = scaleway_rdb_instance.langfuse.id
  name        = "langfuse"
  password    = var.langfuse_db_password
  is_admin    = false
}

resource "scaleway_rdb_privilege" "langfuse" {
  instance_id   = scaleway_rdb_instance.langfuse.id
  user_name     = scaleway_rdb_user.langfuse.name
  database_name = scaleway_rdb_database.langfuse.name
  permission    = "all"
}

# ──────────────────────────────────────────────
# K8s Namespaces (applied via kubectl, not Terraform)
# ──────────────────────────────────────────────
# Two namespaces provide environment isolation:
#   - chatvote-prod: Production Qdrant (10Gi), backend, cronjobs
#     Manifests: k8s/prod/
#   - chatvote-dev:  Staging Qdrant (5Gi), separate API key
#     Manifests: k8s/dev/
#
# Both run on the same cluster and node pool (pool-par-2-8gb).
# Isolation is at the namespace level — separate PVCs, secrets, services.
#
# Apply with:
#   kubectl create namespace chatvote-prod
#   kubectl create namespace chatvote-dev
#   kubectl apply -f k8s/prod/
#   kubectl apply -f k8s/dev/

# ──────────────────────────────────────────────
# Serverless Container — managed by CI/CD
# ──────────────────────────────────────────────
# The serverless container (backend-prod) and its namespace
# are managed by .github/workflows/production-deploy.yml.
# NOT managed by OpenTofu to avoid CI/CD conflicts.
