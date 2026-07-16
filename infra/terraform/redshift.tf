# ---------- Redshift Serverless ----------

resource "aws_redshiftserverless_namespace" "main" {
  namespace_name      = "${var.project}-ns"
  db_name             = var.redshift_db_name
  admin_username      = var.redshift_admin_user
  admin_user_password = var.redshift_admin_password
  iam_roles           = [aws_iam_role.redshift.arn]

  tags = { Name = "${var.project}-redshift-namespace" }
}

resource "aws_redshiftserverless_workgroup" "main" {
  namespace_name = aws_redshiftserverless_namespace.main.namespace_name
  workgroup_name = "${var.project}-wg"
  base_capacity  = var.redshift_base_capacity

  subnet_ids         = aws_subnet.private[*].id
  security_group_ids = [aws_security_group.redshift.id]

  publicly_accessible = false

  tags = { Name = "${var.project}-redshift-workgroup" }
}
