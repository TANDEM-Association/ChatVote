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

output "langfuse_blobs_bucket_endpoint" {
  value       = "https://${scaleway_object_bucket.langfuse_blobs.name}.s3.${var.region}.scw.cloud"
  description = "S3 endpoint for Langfuse blob storage"
}

output "langfuse_db_endpoint" {
  value       = scaleway_rdb_instance.langfuse.endpoint_ip
  description = "Langfuse Managed Database endpoint IP"
}

output "langfuse_db_port" {
  value       = scaleway_rdb_instance.langfuse.endpoint_port
  description = "Langfuse Managed Database port"
}

output "langfuse_db_connection_string" {
  value       = "postgresql://langfuse:${var.langfuse_db_password}@${scaleway_rdb_instance.langfuse.endpoint_ip}:${scaleway_rdb_instance.langfuse.endpoint_port}/langfuse"
  sensitive   = true
  description = "Full DATABASE_URL for Langfuse deployment"
}

output "ragflow_public_ip" {
  value       = var.ragflow_enabled ? scaleway_instance_ip.ragflow[0].address : null
  description = "RAGFlow instance public IP"
}

output "ragflow_url" {
  value       = var.ragflow_enabled ? "http://${scaleway_instance_ip.ragflow[0].address}" : null
  description = "RAGFlow web UI URL"
}
