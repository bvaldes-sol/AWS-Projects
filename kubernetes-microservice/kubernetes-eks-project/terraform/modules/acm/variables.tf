variable "name" {
  description = "Prefix for certificate resources"
  type        = string
}

variable "domain_name" {
  description = "Primary domain (e.g., yourdomain.com)"
  type        = string
}

variable "subject_alternative_names" {
  description = "Additional domains/SANs (e.g., *.yourdomain.com, app.yourdomain.com)"
  type        = list(string)
  default     = []
}

variable "hosted_zone_id" {
  description = "Route 53 hosted zone ID for validation records"
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}