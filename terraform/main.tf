terraform {
  required_version = ">= 1.6.0"

  required_providers {
    scaleway = {
      source  = "scaleway/scaleway"
      version = "~> 2.45"
    }
  }

  # TODO Phase 3: Move state to S3 backend
  # backend "s3" {
  #   bucket                      = "chatvote-tofu-state"
  #   key                         = "terraform.tfstate"
  #   region                      = "fr-par"
  #   endpoint                    = "https://s3.fr-par.scw.cloud"
  #   skip_credentials_validation = true
  #   skip_region_validation      = true
  #   skip_requesting_account_id  = true
  #   skip_metadata_api_check     = true
  #   skip_s3_checksum            = true
  # }
}

# ──────────────────────────────────────────────
# Provider
# ──────────────────────────────────────────────

provider "scaleway" {
  access_key = var.scw_access_key
  secret_key = var.scw_secret_key
  project_id = var.scw_project_id
  region     = var.region
  zone       = var.zone
}
