variable "project_id" {
  description = "GCP project of this environment."
  type        = string
}

variable "region" {
  description = "Region of every resource. us-east4 is the closest GCP region to the organizer's S3 bucket (us-east-2)."
  type        = string
  default     = "us-east4"
}

variable "environment" {
  description = "Environment name; prefixes every resource (factored-<environment>)."
  type        = string
  default     = "dev"
}

variable "image_tag" {
  description = "Tag of the images in Artifact Registry to deploy (the git SHA, set by CI)."
  type        = string
  default     = "latest"
}

variable "db_version" {
  description = "PostgreSQL version of Cloud SQL. 18 was verified locally with asyncpg, psycopg2 and the DuckDB postgres extension."
  type        = string
  default     = "POSTGRES_18"
}

variable "db_tier" {
  description = "Cloud SQL machine tier."
  type        = string
  default     = "db-f1-micro"
}

variable "db_disk_gb" {
  type    = number
  default = 20
}

variable "db_availability_type" {
  description = "ZONAL, or REGIONAL for high availability (roughly double the cost)."
  type        = string
  default     = "ZONAL"
}

variable "db_deletion_protection" {
  type    = bool
  default = false
}

variable "db_point_in_time_recovery" {
  type    = bool
  default = false
}

variable "db_connectivity" {
  description = <<-EOT
    How Cloud Run and the ETL job reach Cloud SQL:
    public_ip  = public IPv4 with db_authorized_networks (what the first stack did)
    connector  = Cloud SQL connector, no network allow-list
    private_ip = private IP over the VPC (Direct VPC egress); the database has no public address
  EOT
  type        = string
  default     = "private_ip"

  validation {
    condition     = contains(["public_ip", "connector", "private_ip"], var.db_connectivity)
    error_message = "db_connectivity must be public_ip, connector or private_ip."
  }
}

variable "subnet_cidr" {
  description = "Application subnet: Cloud Run Direct VPC egress and, later, the Airflow VM. At least a /26."
  type        = string
  default     = "10.10.0.0/24"
}

variable "private_service_cidr" {
  description = "Range reserved for Private Service Access (Cloud SQL private IP)."
  type        = string
  default     = "10.10.1.0/24"
}

variable "enable_nat" {
  description = "Cloud Router and Cloud NAT for instances without an external IP (needed once the Airflow VM exists)."
  type        = bool
  default     = false
}

variable "db_authorized_networks" {
  description = "CIDR ranges allowed over the public IP. Only used when db_connectivity is public_ip."
  type = list(object({
    name = string
    cidr = string
  }))
  default = []
}

variable "backend_public" {
  description = "Open the backend to the internet (allUsers). Off by default: only the agent's service account may call it, with an ID token."
  type        = bool
  default     = false
}

variable "backend_min_instances" {
  type    = number
  default = 0
}

variable "agent_min_instances" {
  type    = number
  default = 0
}

variable "run_deletion_protection" {
  description = "Block terraform destroy on the Cloud Run services."
  type        = bool
  default     = false
}

variable "lakehouse_force_destroy" {
  description = "Allow terraform destroy to delete the bucket together with its objects."
  type        = bool
  default     = true
}

variable "openrouter_api_key" {
  description = "OpenRouter key. Empty means the agent runs on deterministic replies only."
  type        = string
  default     = ""
  sensitive   = true
}

variable "typesafe_api_key" {
  description = "TypeSafe key. Empty means the LLM or keyword classifier is used."
  type        = string
  default     = ""
  sensitive   = true
}

variable "cors_allowed_origins" {
  description = "Exact origins allowed to call the agent from a browser, for example [\"https://app.example.com\"]. Empty turns CORS off. A wildcard is refused by the agent."
  type        = list(string)
  default     = []
}

variable "openrouter_model" {
  description = "The model the agent calls through OpenRouter. The one the evaluation measured (docs/EVALUATION.md); another model is a different system."
  type        = string
  default     = "anthropic/claude-haiku-4.5"
}

variable "guardrail_max_usd" {
  description = "Product decision: auto-resolve only below this USD amount."
  type        = string
  default     = "500"
}

variable "enable_airflow" {
  description = "Deploy Airflow on its own VM (see docs/ARCHITECTURE.md). Needs db_connectivity = private_ip, and turns on Cloud NAT."
  type        = bool
  default     = false
}

variable "airflow_zone" {
  type    = string
  default = "us-east4-a"
}

variable "airflow_machine_type" {
  description = "e2-standard-4 (4 CPU, 16 GB): DuckDB with 8 GB next to the Airflow containers."
  type        = string
  default     = "e2-standard-4"
}

variable "airflow_data_disk_gb" {
  type    = number
  default = 100
}

variable "airflow_auto_stop_cron" {
  description = "Nightly stop of the Airflow VM, in America/Asuncion time. The VM is started by hand (scripts/airflow_vm.sh start)."
  type        = string
  default     = "0 3 * * *"
}

variable "airflow_admin_members" {
  description = "Who may open the IAP tunnel and SSH into the Airflow VM, for example [\"user:name@example.com\"]."
  type        = list(string)
  default     = []
}

variable "db_require_ssl" {
  description = "Refuse unencrypted connections to Cloud SQL."
  type        = bool
  default     = true
}

variable "db_audit_logging" {
  description = "Connection, lock-wait, checkpoint, temp-file and DDL logging on Cloud SQL (changing database flags can restart the instance)."
  type        = bool
  default     = true
}

variable "enable_edge" {
  description = "External Application Load Balancer with Cloud Armor in front of the frontend and the agent (about US$20 a month). When on, both services accept traffic only through it."
  type        = bool
  default     = false
}

variable "edge_domain" {
  description = "Domain of the load balancer's certificate. Empty: <ip>.sslip.io."
  type        = string
  default     = ""
}

variable "edge_lockdown" {
  description = "Send the browser through the load balancer and make the frontend and the agent accept traffic only from it. Turn on once the load balancer answers over HTTPS: its managed certificate takes 15 to 60 minutes to become active, and until then the load balancer cannot serve the application."
  type        = bool
  default     = false
}

variable "service_db_users" {
  description = "The backend and the agent connect with their own database roles (backend_app, agent_app) instead of the owner. Turn on only after infra/gcp/sql/roles.sql has been applied."
  type        = bool
  default     = false
}

variable "demo_accounts_enabled" {
  description = "The backend creates the demonstration accounts at startup and lists them on the sign-in page. The data is synthetic; turn off for anything that is not a demo."
  type        = bool
  default     = true
}

variable "demo_password" {
  description = "Shared password of the demonstration accounts. Public by design: the sign-in page shows it."
  type        = string
  default     = "Demo-Bancario-2026"
}
