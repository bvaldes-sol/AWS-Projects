output "grafana_fqdn" {
  value = "${var.grafana_subdomain}.${var.domain_name}"
}