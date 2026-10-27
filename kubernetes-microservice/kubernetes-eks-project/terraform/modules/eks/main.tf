# EKS Cluster
resource "aws_eks_cluster" "this" {
  name     = var.name
  version  = var.kubernetes_version
  role_arn = var.cluster_role_arn

  vpc_config {
    subnet_ids              = concat(var.private_subnet_ids, var.public_subnet_ids)
    security_group_ids      = []  # Optional custom SGs; AWS creates default
    endpoint_private_access = true
    endpoint_public_access  = var.enable_public_endpoint
    public_access_cidrs     = var.enable_public_endpoint ? ["0.0.0.0/0"] : []  # Restrict in prod
  }

  # Enable control plane logging
  enabled_cluster_log_types = var.enabled_log_types

  tags = merge(var.tags, { Name = var.name })
}

# Managed Node Group
resource "aws_eks_node_group" "default" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "${var.name}-default"
  node_role_arn   = var.node_role_arn
  subnet_ids      = var.private_subnet_ids

  scaling_config {
    desired_size = var.node_group_desired_size
    max_size     = var.node_group_max_size
    min_size     = var.node_group_min_size
  }

  instance_types = var.node_instance_types

  # Use latest EKS-optimized AMI
  ami_type       = "AL2023_x86_64_STANDARD"  # Or BOTTLEROCKET for more secure
  release_version = null  # Latest for the cluster version

  # Update config: Rolling upgrades
  update_config {
    max_unavailable_percentage = 33
  }

  # Disk encryption
  disk_size = 50  # GiB gp3 root volume

  tags = merge(var.tags, { Name = "${var.name}-node-group" })

  depends_on = [aws_eks_cluster.this]
}

# OIDC Provider (for IRSA - pod IAM roles)
data "tls_certificate" "cluster" {
  url = aws_eks_cluster.this.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "this" {
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.cluster.certificates[0].sha1_fingerprint]
  url             = aws_eks_cluster.this.identity[0].oidc[0].issuer

  tags = merge(var.tags, { Name = "${var.name}-oidc" })
}