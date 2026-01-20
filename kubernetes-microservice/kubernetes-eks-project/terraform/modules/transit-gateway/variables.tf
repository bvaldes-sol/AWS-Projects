variable "name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
  description = "Private subnets to associate (for appliance mode if needed)"
}

variable "tags" {
  type    = map(string)
  default = {}
}