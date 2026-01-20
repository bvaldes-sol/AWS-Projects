variable "hosted_zone_id" {
  description = "Route53 hosted zone ID (data source or existing)"
  type        = string
}

variable "domain_name" {
  description = "Base domain (e.g., yourdomain.com)"
  type        = string
}

variable "grafana_subdomain" {
  description = "Subdomain for Grafana"
  type        = string
  default     = "grafana"
}

variable "prometheus_subdomain" {
  description = "Subdomain for Prometheus"
  type        = string
  default     = "prometheus"
}

variable "app_subdomain" {
  description = "Subdomain for sample app (optional)"
  type        = string
  default     = "app"
}

variable "alb_dns_name" {
  description = "ALB DNS name for Ingress (from NGINX or ALB Ingress)"
  type        = string
  default     = ""  # Set from monitoring or separate Ingress module
}

variable "alb_zone_id" {
  description = "Canonical hosted zone ID for the ALB"
  type        = string
  default     = ""  # e.g., Z35SXDOTRQ7X7K for us-east-1; use data source
}

variable "tags" {
  type    = map(string)
  default = {}
}