#provider
variable "region" {
  description = "region for deployment"
  type = string
  default = "us=east-1"
}

variable "vpc_cidr" {
	description = "region for deployment"
  type = string 
  default = "10.0.0.0/16" 
}

variable "cluster_name" { 
	description = "region for deployment"
  type = string 
	default = "portfolio-eks" 
}

variable "domain" { 
	description = "region for deployment"
  type = string 
	default = "yourdomain.com" 
}  

# For Route53
# Add more for subnets, instance types, etc.