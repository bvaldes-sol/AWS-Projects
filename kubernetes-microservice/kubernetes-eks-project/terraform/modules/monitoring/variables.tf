variable "name" {
  description = "Name prefix (e.g., portfolio-eks)"
  type        = string
}

variable "namespace" {
  description = "Kubernetes namespace for monitoring"
  type        = string
  default     = "monitoring"
}

variable "grafana_admin_password" {
  description = "Grafana admin password (sensitive)"
  type        = string
  sensitive   = true
  default     = "admin123"  # Change this! Use random or SSM in prod
}

variable "prometheus_retention" {
  description = "Prometheus data retention period"
  type        = string
  default     = "30d"
}

variable "enable_persistence" {
  description = "Enable persistent storage for Prometheus/Grafana"
  type        = bool
  default     = true
}

variable "ingress_enabled" {
  description = "Enable Ingress for Grafana and Prometheus"
  type        = bool
  default     = true
}

variable "grafana_ingress_host" {
  description = "Host for Grafana Ingress (e.g., grafana.yourdomain.com)"
  type        = string
  default     = ""
}

variable "prometheus_ingress_host" {
  description = "Host for Prometheus Ingress"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Common tags (applied where possible)"
  type        = map(string)
  default     = {}
}