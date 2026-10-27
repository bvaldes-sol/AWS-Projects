# Namespace for monitoring stack
resource "kubernetes_namespace" "this" {
  metadata {
    name = var.namespace
    labels = merge(
      var.tags,
      { name = var.namespace }
    )
  }
}

# Helm release for kube-prometheus-stack (includes Prometheus, Grafana, Alertmanager, etc.)
resource "helm_release" "kube_prometheus_stack" {
  name       = "prometheus"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-prometheus-stack"
  namespace  = kubernetes_namespace.this.metadata[0].name
  version    = "55.5.0"  # Latest stable as of Jan 2026; check https://artifacthub.io/packages/helm/prometheus-community/kube-prometheus-stack for updates

  # Key custom values (override defaults for production-like setup)
  values = [
    yamlencode({
      prometheus = {
        prometheusSpec = {
          retention = var.prometheus_retention
          storageSpec = var.enable_persistence ? {
            volumeClaimTemplate = {
              spec = {
                accessModes = ["ReadWriteOnce"]
                resources = { requests = { storage = "10Gi" } }
              }
            }
          } : null
        }
      }
      grafana = {
        adminPassword = var.grafana_admin_password
        persistence = {
          enabled = var.enable_persistence
          size    = "5Gi"
        }
        ingress = {
          enabled = var.ingress_enabled
          hosts   = [var.grafana_ingress_host]
          annotations = {
            "kubernetes.io/ingress.class" = "nginx"  # Assume NGINX Ingress
            "nginx.ingress.kubernetes.io/ssl-redirect" = "true"
          }
        }
      }
      alertmanager = {
        alertmanagerSpec = {
          storage = var.enable_persistence ? {
            volumeClaimTemplate = {
              spec = {
                accessModes = ["ReadWriteOnce"]
                resources = { requests = { storage = "5Gi" } }
              }
            }
          } : null
        }
      }
      # Optional: Integrate with CloudWatch (via aws-prometheus or sidecar)
      # For now, basic setup; add aws-prometheus-exporter if needed
    })
  ]

  depends_on = [kubernetes_namespace.this]

  # Set sensitive values separately to avoid YAML encoding issues
  set_sensitive {
    name  = "grafana.adminPassword"
    value = var.grafana_admin_password
  }
}

# Optional: Prometheus Ingress if separate from Grafana
resource "kubernetes_ingress_v1" "prometheus" {
  count = var.ingress_enabled && var.prometheus_ingress_host != "" ? 1 : 0

  metadata {
    name      = "prometheus-ingress"
    namespace = var.namespace
    annotations = {
      "kubernetes.io/ingress.class" = "nginx"
    }
  }

  spec {
    rule {
      host = var.prometheus_ingress_host
      http {
        path {
          path      = "/"
          path_type = "Prefix"
          backend {
            service {
              name = "prometheus-kube-prometheus-prometheus"
              port {
                number = 9090
              }
            }
          }
        }
      }
    }
  }
}