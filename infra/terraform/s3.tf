# ---------- S3 Data Lake Bucket ----------

resource "aws_s3_bucket" "data_lake" {
  bucket_prefix = "${var.project}-data-lake-"
  force_destroy = true # Allow terraform destroy to empty and delete

  tags = { Name = "${var.project}-data-lake" }
}

resource "aws_s3_bucket_versioning" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket                  = aws_s3_bucket.data_lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    id     = "archive-raw-data"
    status = "Enabled"
    filter { prefix = "raw/" }

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
  }
}
