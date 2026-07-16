# ---------- EKS Cluster Security Group ----------

resource "aws_security_group" "eks_cluster" {
  name_prefix = "${var.project}-eks-cluster-"
  vpc_id      = aws_vpc.main.id
  description = "EKS cluster control plane"

  tags = { Name = "${var.project}-eks-cluster-sg" }

  lifecycle { create_before_destroy = true }
}

resource "aws_vpc_security_group_ingress_rule" "eks_cluster_nodes" {
  security_group_id            = aws_security_group.eks_cluster.id
  referenced_security_group_id = aws_security_group.eks_nodes.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  description                  = "Nodes to control plane"
}

resource "aws_vpc_security_group_egress_rule" "eks_cluster_all" {
  security_group_id = aws_security_group.eks_cluster.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "All outbound"
}

# ---------- EKS Node Security Group ----------

resource "aws_security_group" "eks_nodes" {
  name_prefix = "${var.project}-eks-nodes-"
  vpc_id      = aws_vpc.main.id
  description = "EKS worker nodes"

  tags = { Name = "${var.project}-eks-nodes-sg" }

  lifecycle { create_before_destroy = true }
}

resource "aws_vpc_security_group_ingress_rule" "nodes_self" {
  security_group_id            = aws_security_group.eks_nodes.id
  referenced_security_group_id = aws_security_group.eks_nodes.id
  ip_protocol                  = "-1"
  description                  = "Node-to-node"
}

resource "aws_vpc_security_group_ingress_rule" "nodes_cluster" {
  security_group_id            = aws_security_group.eks_nodes.id
  referenced_security_group_id = aws_security_group.eks_cluster.id
  ip_protocol                  = "tcp"
  from_port                    = 1025
  to_port                      = 65535
  description                  = "Control plane to nodes"
}

resource "aws_vpc_security_group_egress_rule" "nodes_all" {
  security_group_id = aws_security_group.eks_nodes.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "All outbound"
}

# ---------- Redshift Security Group ----------

resource "aws_security_group" "redshift" {
  name_prefix = "${var.project}-redshift-"
  vpc_id      = aws_vpc.main.id
  description = "Redshift Serverless access"

  tags = { Name = "${var.project}-redshift-sg" }

  lifecycle { create_before_destroy = true }
}

resource "aws_vpc_security_group_ingress_rule" "redshift_from_nodes" {
  security_group_id            = aws_security_group.redshift.id
  referenced_security_group_id = aws_security_group.eks_nodes.id
  ip_protocol                  = "tcp"
  from_port                    = 5439
  to_port                      = 5439
  description                  = "EKS nodes to Redshift"
}

resource "aws_vpc_security_group_egress_rule" "redshift_all" {
  security_group_id = aws_security_group.redshift.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "All outbound"
}
