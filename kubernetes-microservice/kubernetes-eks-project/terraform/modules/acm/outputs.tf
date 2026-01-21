output "certificate_arn" {
  description = "ARN of the validated ACM certificate"
  value       = aws_acm_certificate.this.arn
}

output "certificate_status" {
  value = aws_acm_certificate.this.status
}