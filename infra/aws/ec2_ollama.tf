resource "aws_security_group" "ollama_ec2" {
  name        = "${var.project_name}-ollama-sg"
  description = "Security group for Ollama EC2 instance"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 11434
    to_port     = 11434
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Ollama API"
  }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "SSH"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-ollama-sg"
  }
}

resource "aws_instance" "ollama" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = "t3.medium"
  
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.ollama_ec2.id]
  
  associate_public_ip_address = true
  key_name = "multi-cloud-ai-agent-key"

  user_data = <<-EOF
              #!/bin/bash
              curl -fsSL https://ollama.com/install.sh | sh
              systemctl start ollama
              systemctl enable ollama
              sleep 10
              ollama pull qwen2.5:3b
              EOF

  tags = {
    Name = "${var.project_name}-ollama"
  }
}

output "ollama_public_ip" {
  value       = aws_instance.ollama.public_ip
  description = "Public IP of Ollama EC2 instance"
}

output "ollama_url" {
  value       = "http://${aws_instance.ollama.public_ip}:11434"
  description = "Ollama API URL"
}
