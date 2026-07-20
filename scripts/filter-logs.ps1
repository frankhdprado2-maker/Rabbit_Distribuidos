param([Parameter(Mandatory=$true)][string]$CorrelationId)
docker compose logs --no-color | Select-String -SimpleMatch $CorrelationId
