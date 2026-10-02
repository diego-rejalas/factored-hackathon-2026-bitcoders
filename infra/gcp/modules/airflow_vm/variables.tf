variable "name" {
  description = "Instance name; also the base of the service account id (30 characters or fewer)."
  type        = string
}

variable "project_id" {
  type = string
}

variable "project_number" {
  description = "Project number (not the id): the Compute Engine service agent that runs the schedule is service-<number>@compute-system. Read in the environment, because a data source read inside this module is deferred by its depends_on and would make Terraform replace the IAM binding on every plan."
  type        = string
}

variable "region" {
  type = string
}

variable "zone" {
  type = string
}

variable "machine_type" {
  description = "e2-standard-4 (4 CPU, 16 GB) leaves room for DuckDB with 8 GB next to the Airflow containers."
  type        = string
  default     = "e2-standard-4"
}

variable "boot_disk_gb" {
  type    = number
  default = 30
}

variable "data_disk_gb" {
  description = "Disk for the DuckDB file, the task logs and the Parquet staging area."
  type        = number
  default     = 100
}

variable "network_name" {
  type = string
}

variable "subnetwork_name" {
  type = string
}

variable "image" {
  description = "Airflow image with its tag, in Artifact Registry."
  type        = string
}

variable "registry_repository_id" {
  description = "Artifact Registry repository the VM may read from (and nothing else)."
  type        = string
}

variable "registry_location" {
  type = string
}

variable "lake_bucket" {
  description = "Bucket the pipeline writes its Parquet copies and dbt artifacts to."
  type        = string
}

variable "secret_ids" {
  description = "Short Secret Manager ids by purpose: airflow_db_password, fernet_key, api_jwt_secret, admin_password, pg_password, aws_id, aws_secret."
  type        = map(string)
}

variable "airflow_db_host" {
  description = "Private IP of the Cloud SQL instance that holds Airflow's metadata database."
  type        = string
}

variable "airflow_db_name" {
  type    = string
  default = "airflow"
}

variable "airflow_db_user" {
  type    = string
  default = "airflow"
}

variable "pg_host" {
  description = "Private IP of the serving database the pipeline publishes gold to."
  type        = string
}

variable "pg_port" {
  type    = string
  default = "5432"
}

variable "pg_user" {
  type = string
}

variable "pg_database" {
  type = string
}

variable "duckdb_memory_limit" {
  type    = string
  default = "8GB"
}

variable "duckdb_threads" {
  type    = number
  default = 4
}

variable "admin_members" {
  description = "IAM members (user:... or group:...) allowed to open an IAP tunnel and SSH in with OS Login."
  type        = list(string)
  default     = []
}

variable "auto_stop_enabled" {
  description = "Stop the VM on a schedule so it never runs by forgetting it."
  type        = bool
  default     = true
}

variable "auto_stop_cron" {
  description = "Cron expression of the nightly stop, in auto_stop_time_zone."
  type        = string
  default     = "0 3 * * *"
}

variable "auto_stop_time_zone" {
  type    = string
  default = "America/Asuncion"
}

variable "snapshot_retention_days" {
  type    = number
  default = 7
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "labels" {
  type    = map(string)
  default = {}
}
