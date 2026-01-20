resource "aws_ec2_transit_gateway" "this" {
  description                     = "Transit Gateway for EKS project"
  auto_accept_shared_attachments  = "enable"  # Optional: simplifies sharing
  dns_support                     = "enable"
  vpn_ecmp_support                = "enable"  # For future VPN

  tags = merge(var.tags, { Name = "${var.name}-tgw" })
}

resource "aws_ec2_transit_gateway_vpc_attachment" "this" {
  subnet_ids         = var.subnet_ids
  transit_gateway_id = aws_ec2_transit_gateway.this.id
  vpc_id             = var.vpc_id

  tags = merge(var.tags, { Name = "${var.name}-vpc-attachment" })
}

# Optional: Default route table propagation/association if needed
resource "aws_ec2_transit_gateway_route_table" "default" {
  transit_gateway_id = aws_ec2_transit_gateway.this.id

  tags = merge(var.tags, { Name = "${var.name}-rt" })
}

resource "aws_ec2_transit_gateway_route_table_association" "default" {
  transit_gateway_attachment_id  = aws_ec2_transit_gateway_vpc_attachment.this.id
  transit_gateway_route_table_id = aws_ec2_transit_gateway_route_table.default.id
}