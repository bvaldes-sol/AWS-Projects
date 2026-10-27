variable "name" { 
  type = string 
}

variable "cluster_name" { 
  type = string 
}

variable "oidc_provider_arn" {
  type = string 
}  # From EKS module

variable "oidc_issuer_url" {
 type = string 
}    # From EKS module

variable "vpc_id" {
 type = string 
}

variable "tags" {
 type = map(string)
 default = {} 
}