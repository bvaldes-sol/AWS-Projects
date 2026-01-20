variable "name" { 
  type = string 
}

variable "eks_cluster_name" {
 type = string 
}

variable "alarm_email" {
  type = string 
  default = "" 
}  # For SNS notifications

variable "tags" {
  type = map(string)
  default = {} 
}