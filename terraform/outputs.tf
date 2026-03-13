# ──────────────────────────────────────────────
# Outputs
# ──────────────────────────────────────────────

output "public_assets_bucket_endpoint" {
  value       = "https://${scaleway_object_bucket.public_assets.name}.s3.${var.region}.scw.cloud"
  description = "Public URL base for PDF assets"
}

output "qdrant_snapshots_bucket" {
  value       = scaleway_object_bucket.qdrant_snapshots.name
  description = "Bucket for daily Qdrant snapshots"
}

output "registry_endpoint" {
  value = scaleway_registry_namespace.main.endpoint
}

output "k8s_cluster_id" {
  value = scaleway_k8s_cluster.main.id
}
