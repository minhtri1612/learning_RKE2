output "openvpn_public_ip" {
  value       = aws_eip.openvpn.public_ip
  description = "Elastic IP of OpenVPN server"
}

output "primary_network_interface_id" {
  value       = aws_instance.openvpn.primary_network_interface_id
  description = "ENI for route 10.8.0.0/24 (VPN reply path)"
}

output "openvpn_instance_id" {
  value = aws_instance.openvpn.id
}
