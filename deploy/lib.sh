# Shared choice of compose files: with DOMAIN in .env path B applies (Caddy + HTTPS), otherwise path A.
if grep -q '^DOMAIN=.\+' .env 2>/dev/null; then
  COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
else
  COMPOSE="docker compose"
fi
