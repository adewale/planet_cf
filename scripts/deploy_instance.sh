#!/bin/bash
#
# Deploy a Planet instance to Cloudflare
#
# This script automates all the steps needed to deploy a planet instance:
# 1. Creates D1 database and extracts database_id
# 2. Creates Vectorize index
# 3. Creates queues (feed queue and dead letter queue)
# 4. Prompts for secrets (GitHub OAuth, session secret)
# 5. Runs database migrations
# 6. Deploys the worker
#
# Usage:
#   ./scripts/deploy_instance.sh <instance-id>
#   ./scripts/deploy_instance.sh planet-python
#   ./scripts/deploy_instance.sh planet-python --skip-secrets
#
# Prerequisites:
#   - wrangler CLI installed and authenticated
#   - Instance config created (wrangler.<instance-id>.jsonc)
#   - GitHub OAuth app created (for GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Parse arguments
INSTANCE_ID=""
SKIP_SECRETS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-secrets)
            SKIP_SECRETS=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 <instance-id> [--skip-secrets]"
            echo ""
            echo "Arguments:"
            echo "  instance-id     The instance ID (e.g., planet-python)"
            echo "  --skip-secrets  Skip interactive secret prompts"
            echo ""
            echo "Examples:"
            echo "  $0 planet-python"
            echo "  $0 planet-python --skip-secrets"
            exit 0
            ;;
        *)
            if [[ -z "$INSTANCE_ID" ]]; then
                INSTANCE_ID="$1"
            else
                echo -e "${RED}Error: Unknown argument: $1${NC}"
                exit 1
            fi
            shift
            ;;
    esac
done

if [[ -z "$INSTANCE_ID" ]]; then
    echo -e "${RED}Error: Instance ID is required${NC}"
    echo "Usage: $0 <instance-id>"
    exit 1
fi

CONFIG_FILE="$PROJECT_ROOT/examples/${INSTANCE_ID}/wrangler.jsonc"

# Check prerequisites
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Planet Instance Deployment${NC}"
echo -e "${BLUE}  Instance: ${INSTANCE_ID}${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check wrangler is installed
if ! command -v npx &> /dev/null; then
    echo -e "${RED}Error: npx not found. Please install Node.js and npm.${NC}"
    exit 1
fi

# Check config file exists
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo -e "${RED}Error: Configuration file not found: ${CONFIG_FILE}${NC}"
    echo ""
    # List available examples
    if [[ -d "$PROJECT_ROOT/examples" ]]; then
        echo "Available examples:"
        for dir in "$PROJECT_ROOT/examples"/*/; do
            if [[ -f "${dir}wrangler.jsonc" ]]; then
                example_name=$(basename "$dir")
                echo "  - $example_name"
            fi
        done
        echo ""
    fi
    echo "Create the instance first with:"
    echo "  python scripts/create_instance.py --id ${INSTANCE_ID} --name \"Your Planet Name\""
    echo ""
    echo "Or copy from an existing example:"
    echo "  python scripts/create_instance.py --id ${INSTANCE_ID} --from-example planet-cloudflare"
    exit 1
fi

echo -e "${GREEN}Found config: ${CONFIG_FILE}${NC}"

# Detect lite mode from config file
LITE_MODE=false
if grep -q '"INSTANCE_MODE": "lite"' "$CONFIG_FILE" 2>/dev/null; then
    LITE_MODE=true
    echo -e "${YELLOW}Mode: LITE (no Vectorize, no auth)${NC}"
else
    echo -e "Mode: FULL"
fi
echo ""

# Function to extract UUID from wrangler output
extract_uuid() {
    grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1
}

# Function to update database_id in config
update_database_id() {
    local db_id="$1"
    if [[ -n "$db_id" ]]; then
        # Use sed to replace the database_id
        if [[ "$(uname)" == "Darwin" ]]; then
            # macOS
            sed -i '' "s/\"database_id\": \"[^\"]*\"/\"database_id\": \"${db_id}\"/" "$CONFIG_FILE"
        else
            # Linux
            sed -i "s/\"database_id\": \"[^\"]*\"/\"database_id\": \"${db_id}\"/" "$CONFIG_FILE"
        fi
        echo -e "  ${GREEN}Updated database_id in config${NC}"
    fi
}

# Step 1: Create D1 database
echo -e "${YELLOW}Step 1/7: Creating D1 database...${NC}"
DB_NAME="${INSTANCE_ID}-db"

# Check if database already exists
if npx wrangler d1 info "$DB_NAME" &> /dev/null; then
    echo -e "  ${GREEN}Database already exists: ${DB_NAME}${NC}"
    # Try to extract the ID from info command
    DB_ID=$(npx wrangler d1 info "$DB_NAME" 2>&1 | extract_uuid)
    if [[ -n "$DB_ID" ]]; then
        echo -e "  Database ID: ${DB_ID}"
        update_database_id "$DB_ID"
    fi
else
    OUTPUT=$(npx wrangler d1 create "$DB_NAME" 2>&1) || {
        echo -e "  ${RED}Failed to create database${NC}"
        echo "$OUTPUT"
        exit 1
    }
    DB_ID=$(echo "$OUTPUT" | extract_uuid)
    if [[ -n "$DB_ID" ]]; then
        echo -e "  ${GREEN}Created database: ${DB_NAME}${NC}"
        echo -e "  Database ID: ${DB_ID}"
        update_database_id "$DB_ID"
    else
        echo -e "  ${YELLOW}Warning: Could not extract database ID from output${NC}"
        echo "$OUTPUT"
    fi
fi
echo ""

# Step 2: Create Vectorize index (skip in lite mode)
echo -e "${YELLOW}Step 2/7: Creating Vectorize index...${NC}"
if [[ "$LITE_MODE" == "true" ]]; then
    echo -e "  ${YELLOW}Skipping Vectorize index (lite mode)${NC}"
else
    INDEX_NAME="${INSTANCE_ID}-entries"

    if npx wrangler vectorize info "$INDEX_NAME" &> /dev/null; then
        echo -e "  ${GREEN}Vectorize index already exists: ${INDEX_NAME}${NC}"
    else
        npx wrangler vectorize create "$INDEX_NAME" --dimensions 768 --metric cosine 2>&1 || {
            # May fail if already exists, which is fine
            echo -e "  ${YELLOW}Note: Index may already exist${NC}"
        }
        echo -e "  ${GREEN}Vectorize index ready: ${INDEX_NAME}${NC}"
    fi
fi
echo ""

# Step 3: Create queues
echo -e "${YELLOW}Step 3/7: Creating queues...${NC}"
FEED_QUEUE="${INSTANCE_ID}-feed-queue"
DLQ="${INSTANCE_ID}-feed-dlq"

for QUEUE in "$FEED_QUEUE" "$DLQ"; do
    if npx wrangler queues info "$QUEUE" &> /dev/null 2>&1; then
        echo -e "  ${GREEN}Queue already exists: ${QUEUE}${NC}"
    else
        npx wrangler queues create "$QUEUE" 2>&1 || {
            echo -e "  ${YELLOW}Note: Queue may already exist: ${QUEUE}${NC}"
        }
        echo -e "  ${GREEN}Queue ready: ${QUEUE}${NC}"
    fi
done
echo ""

# Step 4: Set secrets (skip in lite mode)
echo -e "${YELLOW}Step 4/7: Configuring secrets...${NC}"
if [[ "$LITE_MODE" == "true" ]]; then
    echo -e "  ${YELLOW}Skipping secrets (lite mode - no auth required)${NC}"
elif [[ "$SKIP_SECRETS" == "true" ]]; then
    echo -e "  ${YELLOW}Skipping secrets (--skip-secrets flag set)${NC}"
    echo -e "  Remember to set them manually:"
    echo -e "    npx wrangler secret put GITHUB_CLIENT_ID --config $CONFIG_FILE"
    echo -e "    npx wrangler secret put GITHUB_CLIENT_SECRET --config $CONFIG_FILE"
    echo -e "    npx wrangler secret put SESSION_SECRET --config $CONFIG_FILE"
else
    echo "  Setting up GitHub OAuth secrets..."
    echo "  (Create a GitHub OAuth App at: https://github.com/settings/developers)"
    echo ""

    # GITHUB_CLIENT_ID
    echo -n "  Enter GITHUB_CLIENT_ID: "
    read -r GITHUB_CLIENT_ID
    if [[ -n "$GITHUB_CLIENT_ID" ]]; then
        echo "$GITHUB_CLIENT_ID" | npx wrangler secret put GITHUB_CLIENT_ID --config "$CONFIG_FILE" 2>&1 || true
        echo -e "  ${GREEN}Set GITHUB_CLIENT_ID${NC}"
    else
        echo -e "  ${YELLOW}Skipped GITHUB_CLIENT_ID${NC}"
    fi

    # GITHUB_CLIENT_SECRET
    echo -n "  Enter GITHUB_CLIENT_SECRET: "
    read -rs GITHUB_CLIENT_SECRET
    echo ""
    if [[ -n "$GITHUB_CLIENT_SECRET" ]]; then
        echo "$GITHUB_CLIENT_SECRET" | npx wrangler secret put GITHUB_CLIENT_SECRET --config "$CONFIG_FILE" 2>&1 || true
        echo -e "  ${GREEN}Set GITHUB_CLIENT_SECRET${NC}"
    else
        echo -e "  ${YELLOW}Skipped GITHUB_CLIENT_SECRET${NC}"
    fi

    # SESSION_SECRET
    echo -n "  Enter SESSION_SECRET (or press Enter to generate): "
    read -rs SESSION_SECRET
    echo ""
    if [[ -z "$SESSION_SECRET" ]]; then
        SESSION_SECRET=$(openssl rand -hex 32 2>/dev/null || head -c 64 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 64)
        echo -e "  ${BLUE}Generated random session secret${NC}"
    fi
    echo "$SESSION_SECRET" | npx wrangler secret put SESSION_SECRET --config "$CONFIG_FILE" 2>&1 || true
    echo -e "  ${GREEN}Set SESSION_SECRET${NC}"
fi
echo ""

# Step 5: Run migrations
echo -e "${YELLOW}Step 5/7: Running database migrations...${NC}"
MIGRATIONS_DIR="$PROJECT_ROOT/migrations"

if [[ -d "$MIGRATIONS_DIR" ]]; then
    for MIGRATION in "$MIGRATIONS_DIR"/*.sql; do
        if [[ -f "$MIGRATION" ]]; then
            MIGRATION_NAME=$(basename "$MIGRATION")
            echo -e "  Running: ${MIGRATION_NAME}"
            npx wrangler d1 execute "$DB_NAME" --remote --file "$MIGRATION" --config "$CONFIG_FILE" 2>&1 || {
                echo -e "  ${YELLOW}Warning: Migration may have already been applied${NC}"
            }
        fi
    done
    echo -e "  ${GREEN}Migrations complete${NC}"
else
    echo -e "  ${YELLOW}No migrations directory found${NC}"
fi
echo ""

# Step 6: Ensure python_modules symlink exists
echo -e "${YELLOW}Step 6/7: Setting up python_modules symlink...${NC}"
INSTANCE_DIR="$PROJECT_ROOT/examples/${INSTANCE_ID}"
SYMLINK_PATH="$INSTANCE_DIR/python_modules"
TARGET_PATH="../../python_modules"

if [[ -L "$SYMLINK_PATH" ]]; then
    echo -e "  ${GREEN}Symlink already exists: python_modules${NC}"
elif [[ -e "$SYMLINK_PATH" ]]; then
    echo -e "  ${YELLOW}python_modules exists but is not a symlink - skipping${NC}"
else
    ln -s "$TARGET_PATH" "$SYMLINK_PATH" 2>&1 || {
        echo -e "  ${YELLOW}Warning: Could not create symlink${NC}"
    }
    echo -e "  ${GREEN}Created symlink: python_modules -> $TARGET_PATH${NC}"
fi
echo ""

# Step 7: Deploy
echo -e "${YELLOW}Step 7/7: Deploying worker...${NC}"
npx wrangler deploy --config "$CONFIG_FILE" 2>&1 || {
    echo -e "${RED}Deployment failed${NC}"
    exit 1
}
echo ""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Your Planet instance is now live."
echo ""
if [[ "$LITE_MODE" == "true" ]]; then
    echo "Mode: LITE (read-only, no admin interface)"
    echo ""
    echo "Next steps:"
    echo "  1. Visit your worker URL to verify it's working"
    echo "  2. Add feeds directly to the D1 database"
    echo "  3. Configure a custom domain if desired"
else
    echo "Next steps:"
    echo "  1. Visit your worker URL to verify it's working"
    echo "  2. Add feeds via the admin interface (/admin)"
    echo "  3. Configure a custom domain if desired"
fi
echo ""
echo "Useful commands:"
echo "  # View logs"
echo "  npx wrangler tail --config $CONFIG_FILE"
echo ""
echo "  # Redeploy after changes"
echo "  npx wrangler deploy --config $CONFIG_FILE"
