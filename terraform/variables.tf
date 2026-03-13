# ──────────────────────────────────────────────
# Scaleway credentials (via TF_VAR_* env vars)
# ──────────────────────────────────────────────

variable "scw_access_key" {
  type      = string
  sensitive = true
}

variable "scw_secret_key" {
  type      = string
  sensitive = true
}

variable "scw_project_id" {
  type    = string
  default = "78c3d473-15a8-46bf-9c9a-339d618c75b5"
}

variable "region" {
  type    = string
  default = "fr-par"
}

variable "zone" {
  type    = string
  default = "fr-par-2"
}

# ──────────────────────────────────────────────
# K8s cluster
# ──────────────────────────────────────────────

variable "k8s_version" {
  type    = string
  default = "1.35.2"
}

# ──────────────────────────────────────────────
# Qdrant
# ──────────────────────────────────────────────

variable "qdrant_image" {
  type    = string
  default = "qdrant/qdrant:v1.14.0"
}

variable "qdrant_prod_storage_size" {
  type    = string
  default = "10Gi"
}

variable "qdrant_dev_storage_size" {
  type    = string
  default = "5Gi"
}

variable "qdrant_api_key" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Prod Qdrant API key"
}

variable "qdrant_dev_api_key" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Dev Qdrant API key"
}

# ──────────────────────────────────────────────
# Backend
# ──────────────────────────────────────────────

variable "backend_image" {
  type    = string
  default = "rg.fr-par.scw.cloud/chatvote/backend:latest"
}

variable "registry_password" {
  type      = string
  sensitive = true
  default   = ""
}

# ──────────────────────────────────────────────
# S3 / Object Storage
# ──────────────────────────────────────────────

variable "s3_access_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "s3_secret_key" {
  type      = string
  sensitive = true
  default   = ""
}

# ──────────────────────────────────────────────
# Application secrets (for serverless container)
# ──────────────────────────────────────────────

variable "google_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "firebase_credentials_base64" {
  type      = string
  sensitive = true
  default   = ""
}

variable "google_sheets_credentials_base64" {
  type      = string
  sensitive = true
  default   = ""
}

variable "scaleway_embed_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "firecrawl_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "admin_secret" {
  type      = string
  sensitive = true
  default   = ""
}

variable "admin_upload_secret" {
  type      = string
  sensitive = true
  default   = ""
}

variable "google_sheet_id" {
  type    = string
  default = "15Mge7CUwsFMn5h7SVRYoo5V1SyDE2vU5h4F9OnDHWB8"
}

# ──────────────────────────────────────────────
# Serverless container
# ──────────────────────────────────────────────

variable "serverless_memory_limit" {
  type    = number
  default = 4096
}

variable "serverless_min_scale" {
  type    = number
  default = 1
}

variable "serverless_max_scale" {
  type    = number
  default = 3
}
