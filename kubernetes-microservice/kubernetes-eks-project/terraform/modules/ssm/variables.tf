variable "name" {
 type = string 
}

variable "db_password" {
 type = string 
 sensitive = true 
}

variable "tags" {
 type = map(string) 
 default = {} 
}