output "vpc_id" {
  value = aws_vpc.main.id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "public_subnet_a_id" {
  value = aws_subnet.public[0].id
}

output "private_subnet_a_id" {
  value = aws_subnet.private[0].id
}

output "private_subnet_b_id" {
  value = aws_subnet.private[1].id
}

output "private_route_table_id" {
  value       = aws_route_table.private.id
  description = "Dùng để thêm route 10.8.0.0/24 qua OpenVPN sau khi tạo OpenVPN"
}

output "openvpn_sg_id" {
  value = aws_security_group.openvpn.id
}

output "k8s_common_sg_id" {
  value = aws_security_group.k8s_common.id
}

output "k8s_master_sg_id" {
  value = aws_security_group.k8s_master.id
}

output "k8s_worker_sg_id" {
  value = aws_security_group.k8s_worker.id
}

output "web_alb_sg_id" {
  value = aws_security_group.web_alb.id
}
