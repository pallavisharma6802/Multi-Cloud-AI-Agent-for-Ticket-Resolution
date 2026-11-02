terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile
  default_tags { tags = { Project = "resolve-mvp", ManagedBy = "terraform" } }
}

variable "region" {
  type    = string
  default = "us-east-1"
}
variable "aws_profile" {
  type    = string
  default = null
}
variable "name" {
  type    = string
  default = "resolve-mvp"
}
variable "web_cidrs" {
  type        = list(string)
  description = "Explicit HTTP/HTTPS visitor allowlist. A public demo requires an explicit [\"0.0.0.0/0\"] choice. Only ports 80/443 are exposed."
  validation {
    condition     = length(var.web_cidrs) > 0 && alltrue([for cidr in var.web_cidrs : can(cidrnetmask(cidr))])
    error_message = "Supply at least one explicit IPv4 CIDR."
  }
}

data "aws_caller_identity" "current" {}
data "aws_vpc" "default" { default = true }
data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

resource "aws_s3_bucket" "private" {
  bucket        = "${var.name}-${data.aws_caller_identity.current.account_id}"
  force_destroy = false
}
resource "aws_s3_bucket_public_access_block" "private" {
  bucket                  = aws_s3_bucket.private.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "private" {
  bucket = aws_s3_bucket.private.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
resource "aws_s3_bucket_versioning" "private" {
  bucket = aws_s3_bucket.private.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_policy" "tls" {
  bucket = aws_s3_bucket.private.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Deny", Principal = "*", Action = "s3:*",
    Resource  = [aws_s3_bucket.private.arn, "${aws_s3_bucket.private.arn}/*"],
    Condition = { Bool = { "aws:SecureTransport" = "false" } }
  }] })
}
resource "aws_iam_role" "host" {
  name = "${var.name}-host"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole"
  }] })
}
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.host.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
resource "aws_iam_role_policy" "app" {
  role = aws_iam_role.host.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"], Resource = "arn:aws:bedrock:${var.region}::foundation-model/amazon.nova-*" },
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.private.arn },
    { Effect = "Allow", Action = ["s3:GetObject"], Resource = "${aws_s3_bucket.private.arn}/releases/*" },
    { Effect = "Allow", Action = ["s3:PutObject", "s3:GetObject"], Resource = "${aws_s3_bucket.private.arn}/backups/*" }
  ] })
}
resource "aws_iam_instance_profile" "host" {
  name = "${var.name}-host"
  role = aws_iam_role.host.name
}
resource "aws_security_group" "web" {
  name   = "${var.name}-web"
  vpc_id = data.aws_vpc.default.id
  dynamic "ingress" {
    for_each = toset([80, 443])
    content {
      from_port   = ingress.value
      to_port     = ingress.value
      protocol    = "tcp"
      cidr_blocks = var.web_cidrs
    }
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_instance" "app" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = "t3.medium"
  subnet_id                   = sort(data.aws_subnets.default.ids)[0]
  associate_public_ip_address = true
  vpc_security_group_ids      = [aws_security_group.web.id]
  iam_instance_profile        = aws_iam_instance_profile.host.name
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }
  root_block_device {
    volume_type           = "gp3"
    volume_size           = 40
    encrypted             = true
    delete_on_termination = false
  }
  user_data = file("${path.module}/bootstrap.sh")
  tags      = { Name = var.name }
}
resource "aws_eip" "web" {
  domain   = "vpc"
  instance = aws_instance.app.id
}
output "instance_id" { value = aws_instance.app.id }
output "public_ip" { value = aws_eip.web.public_ip }
output "suggested_hostname" { value = "${replace(aws_eip.web.public_ip, ".", "-")}.sslip.io" }
output "release_bucket" { value = aws_s3_bucket.private.id }
output "region" { value = var.region }
