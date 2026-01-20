# Security Group for Jenkins EC2
resource "aws_security_group" "jenkins" {
  name        = "${var.name}-jenkins-sg"
  description = "Security group for Jenkins EC2 instance"
  vpc_id      = var.vpc_id

  # Inbound: Jenkins UI (8080)
  ingress {
    description = "Jenkins UI from allowed IPs"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = var.allowed_ips
  }

  # Inbound: SSH (optional, but useful for troubleshooting; prefer SSM)
  ingress {
    description = "SSH from allowed IPs (optional)"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.allowed_ips
  }

  # Outbound: All traffic
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name}-jenkins-sg" })
}

# EC2 Instance
resource "aws_instance" "jenkins" {
  ami                    = var.ami_id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  iam_instance_profile   = var.iam_instance_profile
  vpc_security_group_ids = [aws_security_group.jenkins.id]

  # Bootstrap script to install and start Jenkins
  user_data = <<-EOF
    #!/bin/bash
    set -e

    # Update and install prerequisites
    apt-get update -y
    apt-get upgrade -y
    apt-get install -y fontconfig openjdk-17-jre wget gnupg

    # Add Jenkins repo
    wget -O /usr/share/keyrings/jenkins-keyring.asc https://pkg.jenkins.io/debian-stable/jenkins.io-2023.key
    echo deb [signed-by=/usr/share/keyrings/jenkins-keyring.asc] https://pkg.jenkins.io/debian-stable binary/ | tee /etc/apt/sources.list.d/jenkins.list > /dev/null

    # Install Jenkins
    apt-get update -y
    apt-get install -y jenkins

    # Start and enable Jenkins
    systemctl daemon-reload
    systemctl enable jenkins
    systemctl start jenkins

    # Optional: Wait for Jenkins to be ready and print initial admin password
    sleep 60
    echo "Jenkins initial admin password:"
    cat /var/lib/jenkins/secrets/initialAdminPassword
  EOF

  user_data_replace_on_change = true  # Recreate instance if user_data changes

  # Root volume: Encrypted, larger for Jenkins jobs/artifacts
  root_block_device {
    volume_size           = 20  # GiB
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  # Enable detailed monitoring (optional, costs extra)
  monitoring = false

  tags = merge(var.tags, { Name = "${var.name}-jenkins" })
}