#!/bin/bash
#
# Set up the test-planet instance for E2E testing.
#
# This wraps deploy_instance.sh with test-specific configuration:
# - Deterministic SESSION_SECRET (matches E2E tests)
# - Dummy GitHub OAuth credentials (E2E tests bypass OAuth via signed cookies)
# - Seeds test data from fixtures
# - Optionally triggers reindex to populate Vectorize
#
# Usage:
#   ./scripts/setup_test_planet.sh              # Full deploy + seed
#   ./scripts/setup_test_planet.sh --seed-only  # Just re-seed data (skip infrastructure)
#   ./scripts/setup_test_planet.sh --local      # Set up for local development
#
# After setup, run E2E tests:
#   npx wrangler dev --remote --config examples/test-planet/wrangler.jsonc
#   RUN_E2E_TESTS=1 uv run pytest tests/e2e/ -v

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
INSTANCE_ID="test-planet"
CONFIG_FILE="$PROJECT_ROOT/examples/${INSTANCE_ID}/wrangler.jsonc"

# H12: the test session secret is NO LONGER committed. It must be supplied via the
# environment so the same value protects the deployed test worker AND is used to
# mint the signed admin cookies the E2E tests / seeder send. Set it before running:
#
#   export SESSION_SECRET="$(openssl rand -hex 32)"
#   ./scripts/setup_test_planet.sh
#
# and pass the SAME value to the tests as E2E_SESSION_SECRET. (SESSION_SECRET is
# preferred; E2E_SESSION_SECRET is accepted as a fallback for symmetry with CI.)
TEST_SESSION_SECRET="${SESSION_SECRET:-${E2E_SESSION_SECRET:-}}"
if [[ -z "$TEST_SESSION_SECRET" ]]; then
    echo -e "${RED}Error: SESSION_SECRET is not set.${NC}" >&2
    echo "  This script no longer ships a default test secret (re-audit H12)." >&2
    echo "  Generate one and re-run, e.g.:" >&2
    echo "    export SESSION_SECRET=\"\$(openssl rand -hex 32)\"" >&2
    echo "    ./scripts/setup_test_planet.sh" >&2
    echo "  Use the SAME value as E2E_SESSION_SECRET when running the tests." >&2
    exit 1
fi

# Parse arguments
SEED_ONLY=false
LOCAL=false
SKIP_REINDEX=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --seed-only)
            SEED_ONLY=true
            shift
            ;;
        --local)
            LOCAL=true
            shift
            ;;
        --skip-reindex)
            SKIP_REINDEX=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--seed-only] [--local] [--skip-reindex]"
            echo ""
            echo "Options:"
            echo "  --seed-only     Skip infrastructure deployment, just seed data"
            echo "  --local         Set up for local development (wrangler dev --local)"
            echo "  --skip-reindex  Skip Vectorize reindex after seeding"
            echo ""
            echo "After setup:"
            echo "  npx wrangler dev --remote --config examples/test-planet/wrangler.jsonc"
            echo "  RUN_E2E_TESTS=1 uv run pytest tests/e2e/ -v"
            exit 0
            ;;
        *)
            echo -e "${RED}Error: Unknown argument: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Test Planet Setup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check config exists
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo -e "${RED}Error: Config not found: ${CONFIG_FILE}${NC}"
    echo "Make sure examples/test-planet/ exists in the repo."
    exit 1
fi

# Step 1: Deploy infrastructure (unless --seed-only)
if [[ "$SEED_ONLY" == "false" ]]; then
    echo -e "${YELLOW}Step 1: Deploying test-planet infrastructure...${NC}"
    "$SCRIPT_DIR/deploy_instance.sh" "$INSTANCE_ID" --skip-secrets
    echo ""

    echo -e "${YELLOW}Step 2: Setting test secrets...${NC}"

    # Set deterministic SESSION_SECRET
    echo "$TEST_SESSION_SECRET" | npx wrangler secret put SESSION_SECRET --config "$CONFIG_FILE" 2>&1 || true
    echo -e "  ${GREEN}Set SESSION_SECRET (deterministic test value)${NC}"

    # Set dummy GitHub OAuth credentials
    # E2E tests bypass OAuth entirely via signed session cookies,
    # so these values don't need to be real.
    echo "test-github-client-id" | npx wrangler secret put GITHUB_CLIENT_ID --config "$CONFIG_FILE" 2>&1 || true
    echo -e "  ${GREEN}Set GITHUB_CLIENT_ID (dummy)${NC}"

    echo "test-github-client-secret" | npx wrangler secret put GITHUB_CLIENT_SECRET --config "$CONFIG_FILE" 2>&1 || true
    echo -e "  ${GREEN}Set GITHUB_CLIENT_SECRET (dummy)${NC}"
    echo ""
else
    echo -e "${YELLOW}Skipping infrastructure deployment (--seed-only)${NC}"
    echo ""
fi

# Step 3: Seed test data
echo -e "${YELLOW}Step 3: Seeding test data...${NC}"

SEED_ARGS=("--db-name" "test-planet-db" "--config" "$CONFIG_FILE")
if [[ "$LOCAL" == "true" ]]; then
    SEED_ARGS+=("--local")
fi

uv run python "$SCRIPT_DIR/seed_test_data.py" "${SEED_ARGS[@]}"
echo ""

# Step 4: Redeploy to pick up any config changes (unless seed-only and local)
if [[ "$SEED_ONLY" == "false" ]]; then
    echo -e "${YELLOW}Step 4: Redeploying worker...${NC}"
    npx wrangler deploy --config "$CONFIG_FILE" 2>&1
    echo ""
fi

# Step 5: Trigger reindex (optional)
if [[ "$SKIP_REINDEX" == "false" && "$LOCAL" == "false" && "$SEED_ONLY" == "false" ]]; then
    echo -e "${YELLOW}Step 5: Waiting for worker to be ready...${NC}"
    sleep 5

    # Get the deployed URL from wrangler
    WORKER_URL=$(npx wrangler deployments list --config "$CONFIG_FILE" 2>&1 | grep -oE 'https://[^[:space:]]+\.workers\.dev' | head -1) || true

    if [[ -n "$WORKER_URL" ]]; then
        echo -e "  Worker URL: ${WORKER_URL}"
        uv run python "$SCRIPT_DIR/seed_test_data.py" \
            --db-name "test-planet-db" \
            --config "$CONFIG_FILE" \
            --reindex \
            --base-url "$WORKER_URL" \
            --session-secret "$TEST_SESSION_SECRET" \
            2>&1 || echo -e "  ${YELLOW}Reindex may need to be triggered manually${NC}"
    else
        echo -e "  ${YELLOW}Could not detect worker URL. Trigger reindex manually:${NC}"
        echo -e "  uv run python scripts/seed_test_data.py --reindex --base-url <YOUR_WORKER_URL> --session-secret \"$TEST_SESSION_SECRET\""
    fi
    echo ""
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Test Planet Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

if [[ "$LOCAL" == "true" ]]; then
    echo "Run local dev server:"
    echo "  npx wrangler dev --local --config examples/test-planet/wrangler.jsonc"
else
    echo "Run local dev with remote bindings:"
    echo "  npx wrangler dev --remote --config examples/test-planet/wrangler.jsonc"
fi
echo ""
echo "Run E2E tests (use the SAME SESSION_SECRET you set above):"
echo "  E2E_SESSION_SECRET=\"\$SESSION_SECRET\" RUN_E2E_TESTS=1 uv run pytest tests/e2e/ -v"
echo ""
