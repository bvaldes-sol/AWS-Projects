# terraform/main.tf

# ────────────────────────────────────────────────────────────────────────────────
# Providers & Data Sources
# ────────────────────────────────────────────────────────────────────────────────

provider "aws" {
  region = "us-east-1"
}

terraform {
  backend "s3" {
    bucket         = "your-terraform-state-bucket-name"  # create manually first
    key            = "eks-portfolio/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}

# Data sources for EKS authentication (used by kubernetes & helm providers)
data "aws_eks_cluster" "cluster" {
  name = module.eks.cluster_id
}

data "aws_eks_cluster_auth" "cluster" {
  name = module.eks.cluster_id
}

provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_ca_certificate)
  token                  = data.aws_eks_cluster_auth.cluster.token
}

provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_ca_certificate)
    token                  = data.aws_eks_cluster_auth.cluster.token
  }
}

# Route53 hosted zone (replace with your domain)
data "aws_route53_zone" "selected" {
  name = var.domain_name  # e.g. "example.com."
}

# Common tags
locals {
  common_tags = {
    Environment = "${var.environment}"
    Project     = "aws-eks-microservice"
    ManagedBy   = "Terraform"
    Owner       = "Cloud-Admin"
  }
}

# ────────────────────────────────────────────────────────────────────────────────
# Modules – in dependency order
# ────────────────────────────────────────────────────────────────────────────────

module "vpc" {
  source = "./modules/vpc"

  name            = var.cluster_name
  cidr            = var.vpc_cidr
  azs             = var.azs
  public_subnets  = var.public_subnet_cidrs
  private_subnets = var.private_subnet_cidrs
  enable_nat_gateway = true
  single_nat_gateway = true

  tags = local.common_tags
}

module "transit_gateway" {
  source = "./modules/transit-gateway"

  name       = var.cluster_name
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnet_ids

  tags = local.common_tags
}

module "s3" {
  source = "./modules/s3"

  name = var.cluster_name
  tags = local.common_tags
}

module "ecr" {
  source = "./modules/ecr"

  name = var.cluster_name
  tags = local.common_tags
}

module "iam" {
  source = "./modules/iam"

  name = var.cluster_name
  tags = local.common_tags
}

module "ec2_jenkins" {
  source = "./modules/ec2-jenkins"

  name                 = var.cluster_name
  subnet_id            = module.vpc.public_subnet_ids[0]
  vpc_id               = module.vpc.vpc_id
  iam_instance_profile = module.iam.jenkins_instance_profile
  allowed_ips          = var.allowed_ips  # e.g. ["203.0.113.0/32"]

  tags = local.common_tags
}

module "rds" {
  source = "./modules/rds"

  name                      = var.cluster_name
  vpc_id                    = module.vpc.vpc_id
  private_subnet_ids        = module.vpc.private_subnet_ids
  allowed_security_group_ids = [module.ec2_jenkins.security_group_id]  # allow Jenkins to connect for testing
  password                  = ""  # I suggest pass this within ssm or pipeline for real deployment

  tags = local.common_tags
}

module "eks" {
  source = "./modules/eks"

  name                    = var.cluster_name
  vpc_id                  = module.vpc.vpc_id
  private_subnet_ids      = module.vpc.private_subnet_ids
  public_subnet_ids       = module.vpc.public_subnet_ids
  cluster_role_arn        = module.iam.eks_cluster_role_arn
  node_role_arn           = module.iam.eks_nodes_role_arn
  node_instance_types     = ["t3.medium"]
  node_group_desired_size = 2
  enable_public_endpoint  = false

  tags = local.common_tags
}

module "ssm" {
  source = "./modules/ssm"

  name        = var.cluster_name
  db_password = module.rds.master_password  # sensitive I suggest pass this within ssm or pipeline for real deployment

  tags = local.common_tags
}

module "monitoring" {
  source = "./modules/monitoring"

  name                   = var.cluster_name
  grafana_admin_password = var.grafana_admin_password  # change this! pw for grafana, I suggest pass this within ssm or pipeline for real deployment
  prometheus_retention   = "30d"
  enable_persistence     = true
  ingress_enabled        = true
  grafana_ingress_host   = "grafana.${var.domain_name}"
  prometheus_ingress_host = "prometheus.${var.domain_name}"

  tags = local.common_tags

  depends_on = [module.eks]  # ensure cluster is ready
}

module "route53" {
  source = "./modules/route53"

  hosted_zone_id    = data.aws_route53_zone.selected.zone_id
  domain_name       = var.domain_name
  alb_dns_name      = "<replace-with-ingress-lb-dns>"  # get from NGINX Ingress or ALB output
  alb_zone_id       = "<replace-with-alb-zone-id>"     # e.g. Z35SXDOTRQ7X7K for us-east-1

  tags = local.common_tags
}

module "cloudwatch" {
  source = "./modules/cloudwatch"

  name             = var.cluster_name
  eks_cluster_name = module.eks.cluster_id
  alarm_email      = var.alarm_notification_email

  tags = local.common_tags
}