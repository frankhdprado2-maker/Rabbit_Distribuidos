$ErrorActionPreference='Stop'
for($i=0;$i -lt 60;$i++){
  try { $health=Invoke-RestMethod http://localhost:8000/health -TimeoutSec 2; if($health.status -eq 'ok'){ exit 0 } } catch {}
  Start-Sleep -Seconds 2
}
throw 'La API no estuvo saludable dentro de 120 segundos.'
