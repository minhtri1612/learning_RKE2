resource "aws_iam_role" "k8s_role" {
  name = "k8s_role_new"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ebs_csi_policy" {
  role       = aws_iam_role.k8s_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

resource "aws_iam_instance_profile" "k8s_profile" {
  name = "k8s_profile_new"
  role = aws_iam_role.k8s_role.name
}

# Bastion Host không cần IAM role đặc biệt - chỉ dùng SSH key