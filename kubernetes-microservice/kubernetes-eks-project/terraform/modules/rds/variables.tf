variable "name" {
  description = "Name prefix for RDS resources"
  type        = string
}

variable "engine_version" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "16.4"  # Latest stable minor as of early 2026; check AWS console/CLI for exact
}

variable "instance_class" {
  description = "DB instance class"
  type        = string
  default     = "db.t3.micro"  # Free Tier eligible; upgrade for prod
}

variable "allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Initial database name"
  type        = string
  default     = "votingdb"
}

variable "username" {
  description = "Master username"
  type        = string
  default     = "admin"
}

variable "password" {
  description = "Master password (provide via tfvars or SSM)"
  type        = string
  sensitive   = true
  default     = ""  # Will use random if empty
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs"
  type        = list(string)
}

variable "allowed_security_group_ids" {
  description = "Security groups allowed to connect (e.g., EKS nodes, EC2)"
  type        = list(string)
  default     = []
}

variable "multi_az" {
  description = "Enable Multi-AZ deployment"
  type        = bool
  default     = false  # Set true for HA in portfolio demo
}

variable "backup_retention_period" {
  description = "Backup retention in days"
  type        = number
  default     = 7
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default     = {}
}