variable "domain_name" {
  description = "domain for hosted zone dns route53"
}

variable "environment" {
  description = "environment deployment is being made in"
}

variable "cluster_name" {
  description = "k8s cluster name"
}

variable "vpc_cidr" {
  description = "cidr block for vpc"
}

variable "azs" {
  description = "availability zones"
}

variable "public_subnet_cidrs" {
  description = "cidr for public subnet"
}

variable "private_subnet_cidrs" {
  description = "cidr for private subnet"
}

variable "allowed_ips" {
  description = "allowed ips to connect to jenkins"
}

variable "grafana_admin_password" {
  description = "pw for grafana, I suggest pass this within ssm or pipeline for real deployment"
}

variable "alarm_notification_email" {
  description = "cloudwatch alarm email sns notification"
}

