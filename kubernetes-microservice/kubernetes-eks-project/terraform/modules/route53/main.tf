# Grafana record (alias to ALB/Ingress)
resource "aws_route53_record" "grafana" {
  zone_id = var.hosted_zone_id
  name    = "${var.grafana_subdomain}.${var.domain_name}"
  type    = "A"

  alias {
    name                   = var.alb_dns_name
    zone_id                = var.alb_zone_id
    evaluate_target_health = true
  }
}

# Prometheus record (similar)
resource "aws_route53_record" "prometheus" {
  zone_id = var.hosted_zone_id
  name    = "${var.prometheus_subdomain}.${var.domain_name}"
  type    = "A"

  alias {
    name                   = var.alb_dns_name
    zone_id                = var.alb_zone_id
    evaluate_target_health = true
  }
}

# Optional app record
resource "aws_route53_record" "app" {
  count   = var.app_subdomain != "" ? 1 : 0
  zone_id = var.hosted_zone_id
  name    = "${var.app_subdomain}.${var.domain_name}"
  type    = "A"

  alias {
    name                   = var.alb_dns_name
    zone_id                = var.alb_zone_id
    evaluate_target_health = true
  }
}