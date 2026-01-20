variable "name" {
  description = "Name prefix for EKS cluster"
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes version for the cluster"
  type        = string
  default     = "1.32"  # Stable as of Jan 2026; options: 1.32, 1.33, 1.34
}

variable "vpc_id" {
  description = "VPC ID from VPC module"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for EKS nodes and control plane"
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "Public subnet IDs (optional for public endpoint/load balancers)"
  type        = list(string)
  default     = []
}

variable "cluster_role_arn" {
  description = "IAM role ARN for EKS cluster"
  type        = string
}

variable "node_role_arn" {
  description = "IAM role ARN for EKS worker nodes"
  type        = string
}

variable "node_group_min_size" {
  description = "Minimum number of nodes"
  type        = number
  default     = 2
}

variable "node_group_max_size" {
  description = "Maximum number of nodes"
  type        = number
  default     = 5
}

variable "node_group_desired_size" {
  description = "Desired number of nodes"
  type        = number
  default     = 2
}

variable "node_instance_types" {
  description = "Instance types for managed node group"
  type        = list(string)
  default     = ["t3.medium"]
}

variable "enable_public_endpoint" {
  description = "Enable public access to cluster endpoint"
  type        = bool
  default     = false  # Private-only recommended for production-like
}

variable "enabled_log_types" {
  description = "Control plane log types to enable"
  type        = list(string)
  default     = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default     = {}
}