# deploy.ps1 — copy files to EC2 and restart the service
# Run from: Main_Project\chatbot\
# Usage: .\deploy.ps1  [-Data]
#
# Configure via environment variables before running:
#   $env:NASCAR_EC2_HOST = "1.2.3.4"                    # EC2 public IP or DNS name
#   $env:NASCAR_EC2_KEY  = "$HOME\.ssh\nascar-ec2.pem"  # path to your SSH key
#   $env:NASCAR_APP_DIR  = "C:\path\to\Main_Project"    # defaults to this script's parent

$EC2_IP  = $env:NASCAR_EC2_HOST
$KEY     = $env:NASCAR_EC2_KEY
$APP_DIR = $env:NASCAR_APP_DIR

if (-not $APP_DIR) { $APP_DIR = Split-Path -Parent $PSScriptRoot }

if (-not $EC2_IP -or -not $KEY) {
  Write-Error "Set NASCAR_EC2_HOST and NASCAR_EC2_KEY before running. See the header of this script."
  exit 1
}

$REMOTE = "ec2-user@${EC2_IP}"

# Copy chatbot source files
Write-Output "Copying chatbot source..."
scp -i $KEY -o StrictHostKeyChecking=no `
  "$APP_DIR\chatbot\app.py" `
  "$APP_DIR\chatbot\agent.py" `
  "$APP_DIR\chatbot\providers.py" `
  "$APP_DIR\chatbot\tools.py" `
  "$APP_DIR\chatbot\data.py" `
  "$APP_DIR\chatbot\requirements.txt" `
  "${REMOTE}:/home/ec2-user/nascar/chatbot/"

# Pass -Data to also sync CSV files (only needed after regenerating CSVs)
if ($args -contains "-Data") {
  Write-Output "Copying CSV data files..."
  scp -i $KEY -o StrictHostKeyChecking=no `
    "$APP_DIR\cup_series_data.csv" `
    "$APP_DIR\xfinity_series_data.csv" `
    "$APP_DIR\truck_series_data.csv" `
    "${REMOTE}:/home/ec2-user/nascar/"
  Write-Output "Copying transformed data..."
  scp -i $KEY -o StrictHostKeyChecking=no -r `
    "$APP_DIR\cup_series_transformed" `
    "${REMOTE}:/home/ec2-user/nascar/"
}

# Restart service
Write-Output "Restarting service..."
ssh -i $KEY -o StrictHostKeyChecking=no $REMOTE "sudo systemctl restart nascar && sudo systemctl status nascar --no-pager"

Write-Output ""
Write-Output "Done. App running at http://$EC2_IP"
