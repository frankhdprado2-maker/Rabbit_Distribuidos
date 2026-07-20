$ErrorActionPreference='Stop'
docker compose stop facturacion-dotnet
$body=@{cliente_id='CLI-RES';nombre_cliente='Prueba Resiliencia';ruc_cliente='20481234567';items=@(@{codigo_articulo='ART-001';cantidad=1})}|ConvertTo-Json -Depth 5
$order=Invoke-RestMethod -Method Post -Uri http://localhost:8000/ordenes -ContentType application/json -Body $body
Start-Sleep -Seconds 8
$pending=docker compose exec -T rabbitmq rabbitmqctl list_queues name messages | Select-String 'cola_facturacion'
if($pending -notmatch '\s[1-9][0-9]*$'){throw "No hay mensaje pendiente: $pending"}
docker compose start facturacion-dotnet
for($i=0;$i -lt 60;$i++){Start-Sleep 2;$state=Invoke-RestMethod "http://localhost:8000/ordenes/$($order.id_orden)";if($state.estado -eq 'CONFIRMADA'){Write-Output $state;exit 0}}
throw 'El flujo no se reanudo.'
