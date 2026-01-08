resource "aws_cloudwatch_dashboard" "k8s_dashboard" {
  dashboard_name = "K8s-Cluster-Dashboard"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = concat(
            [for i in aws_instance.masters : ["AWS/EC2", "CPUUtilization", "InstanceId", i.id, { "label" : "Master-${i.tags.Name}" }]],
            [for i in aws_instance.workers : ["AWS/EC2", "CPUUtilization", "InstanceId", i.id, { "label" : "Worker-${i.tags.Name}" }]]
          )
          view    = "timeSeries"
          stacked = false
          region  = var.region
          title   = "CPU Utilization (Masters & Workers)"
          period  = 300
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = concat(
            [for i in aws_instance.masters : ["AWS/EC2", "NetworkIn", "InstanceId", i.id]],
            [for i in aws_instance.workers : ["AWS/EC2", "NetworkIn", "InstanceId", i.id]]
          )
          view    = "timeSeries"
          stacked = false
          region  = var.region
          title   = "Network In"
          period  = 300
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 24
        height = 6
        properties = {
          metrics = concat(
            [for i in aws_instance.masters : ["AWS/EC2", "StatusCheckFailed", "InstanceId", i.id]],
            [for i in aws_instance.workers : ["AWS/EC2", "StatusCheckFailed", "InstanceId", i.id]]
          )
          view    = "timeSeries"
          stacked = false
          region  = var.region
          title   = "Status Checks Failed"
          period  = 60
        }
      }
    ]
  })
}

resource "aws_cloudwatch_metric_alarm" "high_cpu_masters" {
  count               = var.master_count
  alarm_name          = "high-cpu-master-${count.index + 1}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "This metric monitors ec2 cpu utilization for master nodes"
  dimensions = {
    InstanceId = aws_instance.masters[count.index].id
  }
}

resource "aws_cloudwatch_metric_alarm" "high_cpu_workers" {
  count               = var.worker_count
  alarm_name          = "high-cpu-worker-${count.index + 1}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "This metric monitors ec2 cpu utilization for worker nodes"
  dimensions = {
    InstanceId = aws_instance.workers[count.index].id
  }
}

resource "aws_cloudwatch_metric_alarm" "status_check_failed_masters" {
  count               = var.master_count
  alarm_name          = "status-check-failed-master-${count.index + 1}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "StatusCheckFailed"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "Triggers if status check fails for master nodes"
  dimensions = {
    InstanceId = aws_instance.masters[count.index].id
  }
}

resource "aws_cloudwatch_metric_alarm" "status_check_failed_workers" {
  count               = var.worker_count
  alarm_name          = "status-check-failed-worker-${count.index + 1}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "StatusCheckFailed"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "Triggers if status check fails for worker nodes"
  dimensions = {
    InstanceId = aws_instance.workers[count.index].id
  }
}
