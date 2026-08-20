terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet-group"
  subnet_ids = [aws_subnet.private_1.id, aws_subnet.private_2.id]

  tags = {
    Name = "${var.project_name}-db-subnet-group"
  }
}

resource "aws_security_group" "rds" {
  name        = "${var.project_name}-rds-sg"
  description = "Security group for RDS PostgreSQL"
  vpc_id      = aws_vpc.main.id

  # The app (EC2) reaches Postgres over the private network -- this is the
  # only way in that always exists, regardless of who runs `terraform apply`
  # from where.
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app_ec2.id]
    description     = "travel_booking app"
  }

  # Optional direct access (e.g. psql from your own machine) for the
  # operator's IP only -- never 0.0.0.0/0 (see variables.tf).
  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = var.allowed_management_cidr_blocks
    description = "operator direct access"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-rds-sg"
  }
}

resource "aws_db_instance" "postgres" {
  identifier        = "${var.project_name}-postgres"
  engine            = "postgres"
  # Free Tier: db.t3.micro / db.t4g.micro, up to 20GB gp2/gp3, single-AZ,
  # 750 instance-hours/month -- for 12 months on a new-enough AWS account.
  # Outside that window this becomes a real ongoing cost (~$12-15+/mo).
  instance_class    = "db.t3.micro"
  allocated_storage = 20
  storage_type      = "gp3"
  multi_az          = false # Multi-AZ is NOT Free Tier eligible -- keep this false.

  db_name  = "travel_booking"
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  skip_final_snapshot = true
  # Defaults false; SG still restricts to the app + allowed_management_cidr_blocks.
  publicly_accessible = var.rds_publicly_accessible

  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "mon:04:00-mon:05:00"

  tags = {
    Name = "${var.project_name}-postgres"
  }
}

output "rds_endpoint" {
  value       = aws_db_instance.postgres.endpoint
  description = "RDS PostgreSQL endpoint (host:port)"
}

output "rds_database_name" {
  value       = aws_db_instance.postgres.db_name
  description = "RDS database name"
}

output "travel_database_url" {
  value       = "postgresql://${var.db_username}:${var.db_password}@${aws_db_instance.postgres.endpoint}/${aws_db_instance.postgres.db_name}"
  description = "Full TRAVEL_DATABASE_URL for the app -- set this as the app's env var."
  sensitive   = true
}
