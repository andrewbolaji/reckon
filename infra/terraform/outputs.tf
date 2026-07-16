output "aws_region" {
  value = var.aws_region
}

# --- ECR ---

output "ecr_pipeline_url" {
  value = aws_ecr_repository.repos["pipeline"].repository_url
}

output "ecr_api_url" {
  value = aws_ecr_repository.repos["api"].repository_url
}

output "ecr_dashboard_url" {
  value = aws_ecr_repository.repos["dashboard"].repository_url
}

# --- S3 ---

output "s3_data_lake_bucket" {
  value = aws_s3_bucket.data_lake.id
}

output "s3_data_lake_arn" {
  value = aws_s3_bucket.data_lake.arn
}

# --- EKS ---

output "eks_cluster_name" {
  value = aws_eks_cluster.main.name
}

output "eks_cluster_endpoint" {
  value = aws_eks_cluster.main.endpoint
}

output "eks_cluster_ca" {
  value     = aws_eks_cluster.main.certificate_authority[0].data
  sensitive = true
}

# --- Redshift ---

output "redshift_endpoint" {
  value = aws_redshiftserverless_workgroup.main.endpoint[0].address
}

output "redshift_port" {
  value = aws_redshiftserverless_workgroup.main.endpoint[0].port
}

output "redshift_db_name" {
  value = var.redshift_db_name
}

# --- Convenience: Helm values snippet ---

output "helm_values_snippet" {
  description = "Paste into values-prod.yaml or set via --set"
  value = <<-EOT
    warehouse:
      type: redshift
      host: ${aws_redshiftserverless_workgroup.main.endpoint[0].address}
      port: ${aws_redshiftserverless_workgroup.main.endpoint[0].port}
      db: ${var.redshift_db_name}
      user: ${var.redshift_admin_user}
    lake:
      type: s3
      bucket: ${aws_s3_bucket.data_lake.id}
      region: ${var.aws_region}
    images:
      pipeline: ${aws_ecr_repository.repos["pipeline"].repository_url}
      api: ${aws_ecr_repository.repos["api"].repository_url}
      dashboard: ${aws_ecr_repository.repos["dashboard"].repository_url}
  EOT
  sensitive = true
}
