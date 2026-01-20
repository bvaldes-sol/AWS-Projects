output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.jenkins.id
}

output "public_ip" {
  description = "Public IP of Jenkins instance"
  value       = aws_instance.jenkins.public_ip
}

output "public_dns" {
  description = "Public DNS name"
  value       = aws_instance.jenkins.public_dns
}

output "jenkins_url" {
  description = "Jenkins UI URL (append :8080)"
  value       = "http://${aws_instance.jenkins.public_dns}:8080"
}