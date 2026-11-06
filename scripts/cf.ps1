# Windows equivalent of the Makefile:  .\scripts\cf.ps1 <target>
param([Parameter(Mandatory = $true)][string]$Target)
$ErrorActionPreference = "Stop"
switch ($Target) {
  "up"      { docker compose up -d --build }
  "down"    { docker compose down }
  "logs"    { docker compose logs -f api }
  "migrate" { docker compose exec api alembic upgrade head }
  "seed"    { docker compose exec api python -m app.seed.build }
  "reset"   { docker compose exec api python -m app.seed.build --reset }
  "demo"    { docker compose exec api python -m app.seed.build --reset --demo --paused }
  "test"    { docker compose exec api pytest; Push-Location web; npx playwright test; Pop-Location }
  "record"  { docker compose exec -e AGENT_MODE=record api python -m app.seed.record_demo }
  "sim"     { docker compose run --rm simulator python sim.py --stream --rate 5 }
  "rain"    { docker compose run --rm simulator python sim.py --scenario rain }
  "types"   { Push-Location web; npx openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.d.ts; Pop-Location }
  default   { Write-Error "Unknown target $Target" }
}
