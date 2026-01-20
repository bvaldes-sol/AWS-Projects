resource "aws_ssm_parameter" "db_password" {
  name  = "/${var.name}/rds/master-password"
  type  = "SecureString"
  value = var.db_password

  tags = merge(var.tags, { Name = "${var.name}-db-pass" })
}

# Add more params as needed (e.g., API keys, Jenkins admin token)

