# Bifrost Kubernetes Deployment

This directory contains Kubernetes manifests for deploying Bifrost to a Kubernetes cluster.

## Prerequisites

Before deploying Bifrost, you need:

1. **PostgreSQL Database** - Use a managed service (RDS, Cloud SQL, Azure Database)
2. **S3-Compatible Storage** - AWS S3, GCS, Azure Blob, or MinIO

## Directory Structure

```
k8s/
├── kustomization.yml   # Kustomize configuration
├── namespace.yaml      # Bifrost namespace
├── configmap.yaml      # Non-sensitive configuration
├── secret.yaml         # Secret template (DO NOT commit with values)
├── api/
│   ├── deployment.yaml # FastAPI application
│   └── service.yaml    # ClusterIP service (port 8000)
├── client/
│   ├── deployment.yaml # React frontend (nginx)
│   └── service.yaml    # ClusterIP service (port 80)
├── worker/
│   └── deployment.yaml # Background job workers
├── scheduler/
│   └── deployment.yaml # Cron scheduler (singleton)
├── coding-agent/
│   └── deployment.yaml # Claude Agent SDK container
└── rabbitmq/
    ├── deployment.yaml # RabbitMQ message broker
    └── service.yaml    # ClusterIP service (port 5672, 15672)
```

## Quick Start

### 1. Create Namespace

```bash
kubectl apply -f k8s/namespace.yaml
```

### 2. Configure Secrets

**Option A: kubectl create secret**

```bash
kubectl create secret generic bifrost-secrets \
  --namespace=bifrost \
  --from-literal=BIFROST_SECRET_KEY='your-32-char-secret-key-here' \
  --from-literal=BIFROST_DATABASE_URL='postgresql+asyncpg://user:pass@host:5432/bifrost' \
  --from-literal=BIFROST_DATABASE_URL_SYNC='postgresql://user:pass@host:5432/bifrost' \
  --from-literal=BIFROST_RABBITMQ_URL='amqp://bifrost:pass@rabbitmq:5672/' \
  --from-literal=BIFROST_RABBITMQ_PASSWORD='your-rabbitmq-password' \
  --from-literal=BIFROST_REDIS_URL='redis://redis:6379/0' \
  --from-literal=BIFROST_S3_ENDPOINT_URL='https://s3.us-east-1.amazonaws.com' \
  --from-literal=BIFROST_S3_ACCESS_KEY='your-access-key' \
  --from-literal=BIFROST_S3_SECRET_KEY='your-secret-key'
```

**Option A2: create or update from literals without partial replacement**

This is safer than editing a live secret by hand because it always applies the
full desired secret object in one step:

```bash
kubectl create secret generic bifrost-secrets \
  --namespace=bifrost \
  --from-literal=BIFROST_SECRET_KEY='your-32-char-secret-key-here' \
  --from-literal=BIFROST_DATABASE_URL='postgresql+asyncpg://user:pass@host:5432/bifrost' \
  --from-literal=BIFROST_DATABASE_URL_SYNC='postgresql://user:pass@host:5432/bifrost' \
  --from-literal=BIFROST_RABBITMQ_URL='amqp://bifrost:pass@rabbitmq:5672/' \
  --from-literal=BIFROST_RABBITMQ_PASSWORD='your-rabbitmq-password' \
  --from-literal=BIFROST_REDIS_URL='redis://redis:6379/0' \
  --from-literal=BIFROST_S3_ENDPOINT_URL='https://s3.us-east-1.amazonaws.com' \
  --from-literal=BIFROST_S3_ACCESS_KEY='your-access-key' \
  --from-literal=BIFROST_S3_SECRET_KEY='your-secret-key' \
  --dry-run=client -o yaml | kubectl apply -f -
```

**Option B: Edit and apply secret.yaml**

Edit `k8s/secret.yaml` with your values, then:

```bash
kubectl apply -f k8s/secret.yaml
```

### 2a. Updating Existing Secrets Safely

Avoid ad hoc partial updates unless you are intentionally changing one key and
have already confirmed the rest of the secret is correct. A bad patch can leave
the cluster with a mismatched set of credentials.

Preferred update patterns:

1. Re-apply the full secret manifest with `kubectl apply -f k8s/secret.yaml`.
2. Or re-generate the full secret with `kubectl create secret ... --dry-run=client -o yaml | kubectl apply -f -`.

Use `kubectl patch secret` only for narrow one-key changes when you understand
the current live secret and want to preserve all other keys exactly as-is.

Before changing a live secret, take a backup:

```bash
kubectl get secret bifrost-secrets -n bifrost -o yaml > /tmp/bifrost-secrets.backup.yaml
```

### 2b. Rotating Secrets

Most Bifrost pods consume secrets through `envFrom.secretRef`, so updating the
Kubernetes `Secret` object does not automatically refresh environment variables
inside already-running containers. After updating `bifrost-secrets`, restart the
deployments that consume it:

```bash
kubectl rollout restart deployment/bifrost-api -n bifrost
kubectl rollout restart deployment/bifrost-worker -n bifrost
kubectl rollout restart deployment/bifrost-scheduler -n bifrost
kubectl rollout restart deployment/bifrost-coding-agent -n bifrost
kubectl rollout restart deployment/rabbitmq -n bifrost
```

Wait for the rollouts to finish:

```bash
kubectl rollout status deployment/bifrost-api -n bifrost
kubectl rollout status deployment/bifrost-worker -n bifrost
kubectl rollout status deployment/bifrost-scheduler -n bifrost
kubectl rollout status deployment/bifrost-coding-agent -n bifrost
kubectl rollout status deployment/rabbitmq -n bifrost
```

If you rotate database, RabbitMQ, S3, or OAuth credentials, update the external
service first, then update `bifrost-secrets`, then restart the Bifrost
deployments promptly so old and new credentials do not drift.

### 2c. Secret Rotation Smoke Tests

After a secret change or rotation, run these checks before declaring success:

```bash
# Pods restarted and became Ready
kubectl get pods -n bifrost

# API logs are clean
kubectl logs -n bifrost -l app.kubernetes.io/name=bifrost-api --tail=200

# Worker logs are clean
kubectl logs -n bifrost -l app.kubernetes.io/name=bifrost-worker --tail=200

# Scheduler logs are clean
kubectl logs -n bifrost -l app.kubernetes.io/name=bifrost-scheduler --tail=200
```

Then verify the application at the functional layer:

1. Load the Bifrost UI and confirm login works.
2. Confirm the API can reach PostgreSQL, RabbitMQ, Redis, and S3.
3. Execute one known-good workflow to confirm background execution still works.
4. If OAuth or SSO credentials were rotated, test one login or token refresh path.

### 3. Configure Settings

Edit `k8s/configmap.yaml` to set your S3 bucket and other settings:

```yaml
data:
  BIFROST_S3_BUCKET: "my-bifrost-bucket"
```

Then apply:

```bash
kubectl apply -f k8s/configmap.yaml
```

### 4. Deploy All Services

**Option A: Using Kustomize (recommended)**

```bash
kubectl apply -k k8s/
```

**Option B: Apply individual manifests**

```bash
kubectl apply -f k8s/rabbitmq/
kubectl apply -f k8s/api/
kubectl apply -f k8s/client/
kubectl apply -f k8s/worker/
kubectl apply -f k8s/scheduler/
kubectl apply -f k8s/coding-agent/
```

### 5. Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n bifrost

# Check services
kubectl get svc -n bifrost

# View API logs
kubectl logs -n bifrost -l app.kubernetes.io/name=bifrost-api -f

# View worker logs
kubectl logs -n bifrost -l app.kubernetes.io/name=bifrost-worker -f
```

## Exposing the Application

The manifests don't include an Ingress. Choose your preferred method:

### Option A: Ingress Controller (nginx-ingress)

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: bifrost-ingress
  namespace: bifrost
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "100m"
    nginx.ingress.kubernetes.io/websocket-services: "api"
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - bifrost.example.com
      secretName: bifrost-tls
  rules:
    - host: bifrost.example.com
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: api
                port:
                  number: 8000
          - path: /auth
            pathType: Prefix
            backend:
              service:
                name: api
                port:
                  number: 8000
          - path: /ws
            pathType: Prefix
            backend:
              service:
                name: api
                port:
                  number: 8000
          - path: /
            pathType: Prefix
            backend:
              service:
                name: client
                port:
                  number: 80
```

### Option B: LoadBalancer Service

Change the client service type to LoadBalancer:

```yaml
spec:
  type: LoadBalancer
```

### Option C: Port Forward (Development)

```bash
kubectl port-forward -n bifrost svc/client 3000:80
kubectl port-forward -n bifrost svc/api 8000:8000
```

## Scaling

### API

```bash
kubectl scale deployment bifrost-api -n bifrost --replicas=3
```

### Workers

```bash
kubectl scale deployment bifrost-worker -n bifrost --replicas=5
```

### Scheduler

**WARNING: Do NOT scale the scheduler beyond 1 replica!**

The scheduler must run as a singleton to prevent duplicate job executions.

## Configuration Reference

### Required Secrets

| Name | Description |
|------|-------------|
| `BIFROST_SECRET_KEY` | 32+ char secret for JWT and encryption |
| `BIFROST_DATABASE_URL` | PostgreSQL async connection string |
| `BIFROST_DATABASE_URL_SYNC` | PostgreSQL sync connection string |
| `BIFROST_RABBITMQ_URL` | RabbitMQ AMQP connection string |
| `BIFROST_RABBITMQ_PASSWORD` | RabbitMQ password (for in-cluster deployment) |
| `BIFROST_REDIS_URL` | Redis connection string (for caching) |
| `BIFROST_S3_ENDPOINT_URL` | S3 endpoint (or MinIO URL) |
| `BIFROST_S3_ACCESS_KEY` | S3 access key |
| `BIFROST_S3_SECRET_KEY` | S3 secret key |

### ConfigMap Settings

| Name | Default | Description |
|------|---------|-------------|
| `BIFROST_ENVIRONMENT` | `production` | Environment name |
| `BIFROST_DEBUG` | `false` | Debug mode |
| `BIFROST_S3_BUCKET` | (required) | S3 bucket name for workspace storage |
| `BIFROST_S3_REGION` | `us-east-1` | S3 region |
| `BIFROST_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | JWT access token TTL |
| `BIFROST_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL |
| `BIFROST_MFA_ENABLED` | `true` | Enable MFA |
| `BIFROST_MAX_CONCURRENCY` | `10` | Worker concurrency |
| `BIFROST_WEBAUTHN_RP_ID` | (required) | WebAuthn relying party ID (your domain) |
| `BIFROST_WEBAUTHN_RP_NAME` | `Bifrost` | WebAuthn display name |
| `BIFROST_WEBAUTHN_ORIGIN` | (required) | WebAuthn origin URL (e.g., https://bifrost.example.com) |
| `BIFROST_PUBLIC_URL` | (required) | Public URL for the Bifrost platform |

## Troubleshooting

### Pods stuck in Pending

Check for resource constraints:

```bash
kubectl describe pod -n bifrost <pod-name>
```

### Database connection errors

1. Verify the database is accessible from the cluster
2. Check the connection string in secrets
3. Ensure the database user has proper permissions

### Migrations not running

The API init container runs migrations. Check its logs:

```bash
kubectl logs -n bifrost <api-pod-name> -c migrate
```

### Workers not processing jobs

1. Check RabbitMQ connection
2. Verify worker logs for errors
3. Ensure the queue exists in RabbitMQ
