variable "name" {
  description = "Name prefix for resources (e.g., portfolio-eks)"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.micro"  # Cost-effective; upgrade for heavier Jenkins usage
}

variable "ami_id" {
  description = "AMI ID (Ubuntu recommended for Jenkins)"
  type        = string
  default     = "ami-053b0d53c279acc90"  # Ubuntu 22.04 LTS us-east-1 (update via data source in root if needed)
}

variable "subnet_id" {
  description = "Public subnet ID from VPC module"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID (for security group)"
  type        = string
}

variable "iam_instance_profile" {
  description = "IAM instance profile name (from IAM module)"
  type        = string
}

variable "allowed_ips" {
  description = "CIDR blocks allowed to access Jenkins UI (8080) and SSH (22, optional)"
  type        = list(string)
  default     = ["0.0.0.0/0"]  # Restrict to your IP in production, e.g., ["203.0.113.0/24"]
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default     = {}
}