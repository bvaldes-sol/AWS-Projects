# Random password if not provided
resource "random_password" "db_password" {
  count   = var.password == "" ? 1 : 0
  length  = 16
  special = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

locals {
  final_password = var.password != "" ? var.password : random_password.db_password[0].result
}

# Subnet group for RDS (private subnets)
resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-rds-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = merge(var.tags, { Name = "${var.name}-rds-subnet-group" })
}

# Security Group for RDS
resource "aws_security_group" "rds" {
  name        = "${var.name}-rds-sg"
  description = "Security group for RDS PostgreSQL"
  vpc_id      = var.vpc_id

  # Inbound: PostgreSQL (5432) from allowed SGs (e.g., EKS, EC2)
  ingress {
    description     = "PostgreSQL from app/EC2/EKS"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = var.allowed_security_group_ids
  }

  # Outbound: All (for replication, etc.)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name}-rds-sg" })
}

# Parameter group (optional custom params)
resource "aws_db_parameter_group" "this" {
  name   = "${var.name}-pg16-params"
  family = "postgres16"

  # Example custom params
  parameter {
    name  = "log_connections"
    value = "1"
  }

  parameter {
    name  = "log_disconnections"
    value = "1"
  }

  tags = merge(var.tags, { Name = "${var.name}-pg-params" })
}

# Main RDS Instance
resource "aws_db_instance" "this" {
  identifier             = "${var.name}-postgres"
  engine                 = "postgres"
  engine_version         = var.engine_version
  instance_class         = var.instance_class
  allocated_storage      = var.allocated_storage
  storage_type           = "gp3"
  storage_encrypted      = true

  db_name                = var.db_name
  username               = var.username
  password               = local.final_password
  port                   = 5432

  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.this.name

  multi_az               = var.multi_az
  publicly_accessible    = false

  backup_retention_period = var.backup_retention_period
  backup_window           = "03:00-04:00"  # UTC; adjust to your timezone preference
  maintenance_window      = "Mon:04:00-Mon:05:00"

  parameter_group_name    = aws_db_parameter_group.this.name

  # Performance insights (optional, costs extra)
  performance_insights_enabled = false

  # Deletion protection for safety
  deletion_protection = false  # Set true in prod

  # Skip final snapshot on destroy (for dev/portfolio)
  skip_final_snapshot = true

  tags = merge(var.tags, { Name = "${var.name}-rds" })
}