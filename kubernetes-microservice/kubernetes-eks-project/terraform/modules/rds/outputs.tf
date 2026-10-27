output "db_instance_id" {
  description = "RDS instance ID"
  value       = aws_db_instance.this.id
}

output "endpoint" {
  description = "RDS endpoint (host:port)"
  value       = aws_db_instance.this.endpoint
}

output "address" {
  description = "RDS hostname"
  value       = aws_db_instance.this.address
}

output "arn" {
  description = "RDS ARN"
  value       = aws_db_instance.this.arn
}

output "master_password" {
  description = "Generated master password (sensitive)"
  value       = local.final_password
  sensitive   = true
}