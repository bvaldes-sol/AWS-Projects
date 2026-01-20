variable "vpc_cidr" {
  description = "cidr for vpc"
}

variable "region" {
  description = "region for deployment"
}

variable "envrionment" {
  description = "env for deployment"
}

variable "cidr_private_1a" {
  description = "cidr block for subnet within specified az"
}

variable "cidr_private_1b" {
  description = "cidr block for subnet within specified az"
}

variable "cidr_public_1a" {
  description = "cidr block for subnet within specified az"
}

variable "cidr_public_1b" {
  description = "cidr block for subnet within specified az"
}