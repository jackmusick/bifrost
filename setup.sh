#!/bin/bash
# Bifrost Setup Script
# Generates .env file with secure random secrets and domain configuration

set -e

ENV_FILE=".env"
ENV_EXAMPLE=".env.example"

echo "Bifrost Setup"
echo "============="
echo ""

# Check if .env already exists
if [ -f "$ENV_FILE" ]; then
    read -p ".env already exists. Overwrite? (y/N): " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "Setup cancelled."
        exit 0
    fi
fi

# Check if .env.example exists
if [ ! -f "$ENV_EXAMPLE" ]; then
    echo "Error: $ENV_EXAMPLE not found"
    exit 1
fi

# Copy example
cp "$ENV_EXAMPLE" "$ENV_FILE"

# Prompt for domain configuration
echo "Domain Configuration"
echo "--------------------"
echo "Passkeys (WebAuthn) require your domain to be configured correctly."
echo "For local development, use 'localhost'. For production, use your domain."
echo ""
read -p "Enter your domain (e.g., localhost, app.example.com) [localhost]: " DOMAIN
DOMAIN=${DOMAIN:-localhost}

# Determine protocol based on domain
if [ "$DOMAIN" = "localhost" ] || [ "$DOMAIN" = "127.0.0.1" ]; then
    ORIGIN="http://${DOMAIN}:3000"
    ENVIRONMENT="development"
else
    ORIGIN="https://${DOMAIN}"
    ENVIRONMENT="production"
fi

echo ""
echo "Using:"
echo "  Domain (RP ID): $DOMAIN"
echo "  Origin: $ORIGIN"
echo "  Environment: $ENVIRONMENT"
echo ""

# Generate secure random values (alphanumeric only for compatibility)
POSTGRES_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)
RABBITMQ_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)
MINIO_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)
SECRET_KEY=$(openssl rand -base64 48 | tr -dc 'a-zA-Z0-9' | head -c 48)

# Replace in .env (sed -i.bak works on both Linux and macOS)
sed -i.bak "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$POSTGRES_PASS/" "$ENV_FILE"
sed -i.bak "s/RABBITMQ_PASSWORD=.*/RABBITMQ_PASSWORD=$RABBITMQ_PASS/" "$ENV_FILE"
sed -i.bak "s/MINIO_ROOT_PASSWORD=.*/MINIO_ROOT_PASSWORD=$MINIO_PASS/" "$ENV_FILE"
sed -i.bak "s/BIFROST_SECRET_KEY=.*/BIFROST_SECRET_KEY=$SECRET_KEY/" "$ENV_FILE"

# Configure WebAuthn/Passkeys
sed -i.bak "s|BIFROST_WEBAUTHN_RP_ID=.*|BIFROST_WEBAUTHN_RP_ID=$DOMAIN|" "$ENV_FILE"
sed -i.bak "s|BIFROST_WEBAUTHN_ORIGIN=.*|BIFROST_WEBAUTHN_ORIGIN=$ORIGIN|" "$ENV_FILE"

# Set environment
sed -i.bak "s/BIFROST_ENVIRONMENT=.*/BIFROST_ENVIRONMENT=$ENVIRONMENT/" "$ENV_FILE"

rm -f "$ENV_FILE.bak"

echo "✓ Created .env with secure secrets"
echo ""
echo "Generated:"
echo "  - POSTGRES_PASSWORD (24 chars)"
echo "  - RABBITMQ_PASSWORD (24 chars)"
echo "  - MINIO_ROOT_PASSWORD (24 chars)"
echo "  - BIFROST_SECRET_KEY (48 chars)"
echo ""
echo "Configured:"
echo "  - BIFROST_WEBAUTHN_RP_ID=$DOMAIN"
echo "  - BIFROST_WEBAUTHN_ORIGIN=$ORIGIN"
echo "  - BIFROST_ENVIRONMENT=$ENVIRONMENT"
echo ""
echo "Next steps:"
echo "  docker compose up"
echo ""
if [ "$DOMAIN" = "localhost" ]; then
    echo "Access the platform at http://localhost:3000"
else
    echo "Access the platform at https://$DOMAIN"
fi
