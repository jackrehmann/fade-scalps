terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

# Security group for EC2 instance
resource "aws_security_group" "fade_analyzer_sg" {
  name_prefix = "fade-analyzer-"

  # SSH access
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Outbound internet access
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# IAM role for EC2 instance
resource "aws_iam_role" "fade_analyzer_role" {
  name = "fade-analyzer-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
}

# Instance profile
resource "aws_iam_instance_profile" "fade_analyzer_profile" {
  name = "fade-analyzer-profile"
  role = aws_iam_role.fade_analyzer_role.name
}

# EC2 instance
resource "aws_instance" "fade_analyzer" {
  ami                    = "ami-0c02fb55956c7d316" # Amazon Linux 2023
  instance_type          = "t3.micro"
  security_groups        = [aws_security_group.fade_analyzer_sg.name]
  iam_instance_profile   = aws_iam_instance_profile.fade_analyzer_profile.name
  key_name               = "your-key-pair" # Replace with your key pair name

  user_data = <<-EOF
              #!/bin/bash
              yum update -y
              yum install -y python3 python3-pip git
              pip3 install requests openai
              EOF

  tags = {
    Name = "fade-analyzer"
  }
}

output "instance_ip" {
  value = aws_instance.fade_analyzer.public_ip
}

output "instance_dns" {
  value = aws_instance.fade_analyzer.public_dns
}