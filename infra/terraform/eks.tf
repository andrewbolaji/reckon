# ---------- EKS Cluster ----------

resource "aws_eks_cluster" "main" {
  name     = "${var.project}-cluster"
  role_arn = aws_iam_role.eks_cluster.arn
  version  = "1.30"

  vpc_config {
    subnet_ids = concat(
      aws_subnet.public[*].id,
      aws_subnet.private[*].id
    )
    security_group_ids      = [aws_security_group.eks_cluster.id]
    endpoint_public_access  = true
    endpoint_private_access = true
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_cluster_policy,
    aws_iam_role_policy_attachment.eks_vpc_controller,
  ]
}

# ---------- Node Launch Template ----------
# Codifies two fixes that previously needed post-apply runtime patches:
#  - IMDSv2 hop limit 2 so pods (one network hop from the node) can reach the
#    instance metadata service and assume the node role for S3 access. The EKS
#    default hop limit of 1 drops the token response before it reaches a pod.
#  - Attaches the custom eks_nodes security group to the worker ENIs. That SG is
#    what the redshift_from_nodes ingress rule authorizes on 5439; without it the
#    nodes carry only the EKS-managed cluster SG and cannot reach Redshift.
resource "aws_launch_template" "nodes" {
  name_prefix = "${var.project}-nodes-"

  vpc_security_group_ids = [aws_security_group.eks_nodes.id]

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ---------- Managed Node Group ----------

resource "aws_eks_node_group" "main" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.project}-nodes"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = aws_subnet.private[*].id

  instance_types = [var.eks_node_instance_type]

  scaling_config {
    desired_size = var.eks_desired_nodes
    min_size     = var.eks_min_nodes
    max_size     = var.eks_max_nodes
  }

  update_config {
    max_unavailable = 1
  }

  # instance_types stays on the node group (setting it in the launch template
  # too would conflict); the LT supplies metadata options + the node SG.
  launch_template {
    id      = aws_launch_template.nodes.id
    version = aws_launch_template.nodes.latest_version
  }

  depends_on = [
    aws_iam_role_policy_attachment.node_worker,
    aws_iam_role_policy_attachment.node_cni,
    aws_iam_role_policy_attachment.node_ecr,
  ]

  tags = { Name = "${var.project}-node-group" }
}
