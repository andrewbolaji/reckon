variable "project" {
  description = "Project name, used as prefix for all resources"
  type        = string
  default     = "reckon"
}

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

# --- EKS ---

variable "eks_node_instance_type" {
  description = "EC2 instance type for EKS worker nodes"
  type        = string
  default     = "t3.medium"
}

variable "eks_desired_nodes" {
  description = "Desired number of EKS worker nodes"
  type        = number
  default     = 2
}

variable "eks_min_nodes" {
  type    = number
  default = 1
}

variable "eks_max_nodes" {
  type    = number
  default = 3
}

# --- Redshift Serverless ---

variable "redshift_admin_user" {
  description = "Redshift admin username"
  type        = string
  default     = "reckon_admin"
}

variable "redshift_admin_password" {
  description = "Redshift admin password"
  type        = string
  sensitive   = true
}

variable "redshift_db_name" {
  description = "Redshift database name"
  type        = string
  default     = "reckon"
}

variable "redshift_base_capacity" {
  description = "Redshift Serverless base RPU capacity (8 is minimum)"
  type        = number
  default     = 8
}

# --- Networking ---

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "AZs to use (need at least 2 for EKS)"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}
