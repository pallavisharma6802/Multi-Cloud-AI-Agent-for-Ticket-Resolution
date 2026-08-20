# Hosts the travel_booking FastAPI app. Replaces the old ec2_ollama.tf
# (t3.medium, not Free Tier eligible, unused) -- this is t3.micro, which is.

# Generated here (not a pre-existing key pair someone has to already have)
# so `terraform apply` works from a clean AWS account. Private key is written
# locally as a Terraform output file, gitignored -- see variables.tf.
resource "tls_private_key" "app" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "app" {
  key_name   = "${var.project_name}-app-key"
  public_key = tls_private_key.app.public_key_openssh
}

resource "local_sensitive_file" "app_private_key" {
  content         = tls_private_key.app.private_key_pem
  filename        = "${path.module}/${var.project_name}-app-key.pem"
  file_permission = "0400"
}

# Bedrock-only role for the RUNNING APP -- deliberately narrower than the
# infra-deploy credentials used to create this infrastructure. No AWS keys
# are stored on the instance at all; boto3 picks this role up automatically
# via the instance metadata service.
resource "aws_iam_role" "app" {
  name = "${var.project_name}-app-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "app_bedrock" {
  name = "${var.project_name}-app-bedrock-invoke"
  role = aws_iam_role.app.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
      Resource = "*"
    }]
  })
}

# Lets you reach the instance via `aws ssm start-session` with no open SSH
# port and no key pair needed for day-to-day access (the key pair above is
# a fallback for the initial code deploy / debugging).
resource "aws_iam_role_policy_attachment" "app_ssm" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "app" {
  name = "${var.project_name}-app-profile"
  role = aws_iam_role.app.name
}

resource "aws_security_group" "app_ec2" {
  name        = "${var.project_name}-app-sg"
  description = "Security group for the travel_booking app EC2 instance"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = var.app_port
    to_port     = var.app_port
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # public web app -- this port is meant to be reached by anyone
    description = "app HTTP"
  }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.allowed_management_cidr_blocks
    description = "SSH (fallback -- prefer SSM Session Manager)"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-app-sg"
  }
}

resource "aws_instance" "app" {
  ami           = data.aws_ami.ubuntu.id
  # Free Tier: t3.micro / t2.micro, 750 instance-hours/month for 12 months
  # on a new-enough AWS account. Outside that window this is a real cost.
  instance_type = "t3.micro"

  subnet_id                  = aws_subnet.public.id
  vpc_security_group_ids     = [aws_security_group.app_ec2.id]
  iam_instance_profile       = aws_iam_instance_profile.app.name
  associate_public_ip_address = true
  key_name                   = aws_key_pair.app.key_name

  # Prepares the runtime (Python, a venv, a systemd unit pointed at
  # /opt/travel_booking) but does NOT put app code on the box -- that's
  # shipped separately (rsync/scp) since it isn't in a git remote this
  # instance can pull from. The service is enabled but will fail to start
  # until the code + a real /etc/travel-booking.env exist; that's expected
  # until the deploy step runs.
  user_data = <<-EOF
              #!/bin/bash
              set -e
              apt-get update -y
              apt-get install -y python3.11 python3.11-venv python3-pip rsync

              mkdir -p /opt/travel_booking
              chown ubuntu:ubuntu /opt/travel_booking

              cat > /etc/systemd/system/travel-booking.service <<UNIT
              [Unit]
              Description=travel_booking FastAPI app
              After=network.target

              [Service]
              Type=simple
              User=ubuntu
              WorkingDirectory=/opt/travel_booking
              EnvironmentFile=/etc/travel-booking.env
              ExecStart=/opt/travel_booking/venv/bin/uvicorn travel_booking.api:app --host 0.0.0.0 --port ${var.app_port}
              Restart=on-failure
              RestartSec=5

              [Install]
              WantedBy=multi-user.target
              UNIT

              systemctl daemon-reload
              systemctl enable travel-booking.service
              EOF

  tags = {
    Name = "${var.project_name}-app"
  }
}

output "app_public_ip" {
  value       = aws_instance.app.public_ip
  description = "Public IP of the travel_booking app instance"
}

output "app_url" {
  value       = "http://${aws_instance.app.public_ip}:${var.app_port}"
  description = "URL to reach the deployed app"
}

output "ssh_key_path" {
  value       = local_sensitive_file.app_private_key.filename
  description = "Local path to the private key for SSH (fallback) or scp"
}
