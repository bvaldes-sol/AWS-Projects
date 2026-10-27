output "namespace" {
  value = var.namespace
}

output "grafana_url" {
  description = "Grafana access URL (if Ingress enabled)"
  value       = var.ingress_enabled ? "https://${var.grafana_ingress_host}" : "Use port-forward: kubectl port-forward svc/prometheus-grafana -n monitoring 3000:80"
}

output "prometheus_url" {
  description = "Prometheus access URL"
  value       = var.ingress_enabled && var.prometheus_ingress_host != "" ? "https://${var.prometheus_ingress_host}" : "Use port-forward: kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n monitoring 9090"
}