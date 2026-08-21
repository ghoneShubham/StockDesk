# Cost report (Day 15)

Target spend for the three-week build: **$6–9** in `ap-south-1`. Hard stop to investigate if approaching **$15**.

## Actual spend (fill at demo)

| Item | Approx |
|---|---|
| EC2 `t3.micro` (hours × rate) | $_ |
| gp3 20 GB | $_ |
| Elastic IP (if allocated while instance stopped) | $_ |
| S3 (media + backups) | $_ |
| SES (sandbox sends) | ~$0 |
| Data transfer | $_ |
| **Total** | **$_** |

Record the AWS Billing/Cost Explorer total for the project window here before Review 3.

## How to roughly halve cost

1. **Stop the EC2 instance** when not demoing (biggest lever). Use an **Elastic IP** so DNS does not break on restart.
2. Keep **no RDS / NAT / ALB** (already avoided).
3. Short **backup retention** (`BACKUP_RETENTION_DAYS=3`–`7`) and delete unused S3 objects.
4. Prefer **spot** only if acceptable for demo risk; otherwise stick to stop/start discipline.
5. Turn off unused Elastic IPs and extra volumes.

Budget alerts at **$5** and **$10** should already be set (RUNBOOK §1).
