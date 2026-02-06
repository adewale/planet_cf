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

set -e

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

# Deterministic test secret - MUST match E2E_SESSION_SECRET default in tests/e2e/conftest.py
TEST_SESSION_SECRET="test-session-secret-for-e2e-testing-only"

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
    WORKER_URL=$(npx wrangler deployments list --config "$CONFIG_FILE" 2>&1 | grep -oP 'https://[^\s]+\.workers\.dev' | head -1 || true)

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
echo "Run E2E tests:"
echo "  RUN_E2E_TESTS=1 uv run pytest tests/e2e/ -v"
echo ""
echo "Session secret for E2E tests:"
echo "  E2E_SESSION_SECRET=\"$TEST_SESSION_SECRET\""
echo ""
