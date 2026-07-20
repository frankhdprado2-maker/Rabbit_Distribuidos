param([ValidateSet('up','down','rebuild','seed','test','logs','clean','status')][string]$Action='up')
$ErrorActionPreference='Stop'
switch($Action){
  'up' { docker compose up --build -d }
  'down' { docker compose down }
  'rebuild' { docker compose build --no-cache; docker compose up -d }
  'seed' { docker compose restart inventario-java }
  'test' { python tests/integration/e2e.py }
  'logs' { docker compose logs -f }
  'clean' { docker compose down -v --remove-orphans }
  'status' { docker compose ps }
}
