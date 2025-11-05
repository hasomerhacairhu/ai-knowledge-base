# Cloudflare Tunnel Setup for AI Knowledge Base API

## 🔄 Updated Configuration

The registry compose file has been updated to:

1. **Removed External Apps Network**: No longer depends on external `apps` network
2. **Added Cloudflare Tunnel Service**: Integrated `cloudflared` container  
3. **Internal Network Only**: API uses only `ai-kb-network` for internal communication
4. **Profile-based Deployment**: Use `--profile tunnel` to enable Cloudflare Tunnel

## ✅ New Architecture

- **API Container**: Accessible internally at `http://api:8000` within `ai-kb-network`
- **Cloudflare Tunnel**: Routes external traffic to internal API service
- **No External Networks**: Self-contained deployment

## 🔧 Environment Setup

Before deploying with Cloudflare Tunnel, configure your environment variables:

```bash
# Copy the example file
cp .env.example .env

# Edit the .env file with your values
# Required for Cloudflare Tunnel:
CLOUDFLARE_TUNNEL_TOKEN=your_cloudflare_tunnel_token_here
API_BASE_URL=https://api.yourdomain.com/api

# Other required variables...
OPENAI_API_KEY=sk-proj-...
# ... etc
```

## 🔧 Configure Cloudflare Tunnel

To expose the API through Cloudflare Tunnel:

### Option 1: Via Cloudflare Dashboard (Recommended)

1. **Go to Cloudflare Zero Trust Dashboard**:
   - Navigate to https://one.dash.cloudflare.com/
   - Go to **Networks** → **Tunnels**
   - Find your tunnel (it's already running based on the token)

2. **Add a Public Hostname**:
   - Click on your tunnel
   - Go to the **Public Hostname** tab
   - Click **Add a public hostname**
   - Configure:
     - **Subdomain**: `ai-kb-api` (or your preferred name)
     - **Domain**: Select your domain
     - **Type**: `HTTP`
     - **URL**: `http://ai-kb-api:8000`
   - Save

3. **Test the endpoint**:
   ```bash
   curl https://ai-kb-api.yourdomain.com/health
   ```

### Option 2: Integrated Compose Deployment (New)

The registry compose file now includes Cloudflare Tunnel as a service:

1. **Set Environment Variable**:
   ```bash
   # Add to your .env file
   echo "CLOUDFLARE_TUNNEL_TOKEN=your_tunnel_token_here" >> .env
   ```

2. **Deploy with Tunnel**:
   ```bash
   # Start registry services with Cloudflare Tunnel
   docker-compose -f docker-compose.from-registry.yml --profile tunnel up -d
   
   # Check tunnel status
   docker logs ai-kb-cloudflared
   ```

3. **Configure Public Hostname** (via Cloudflare Dashboard):
   - Go to Zero Trust Dashboard → Networks → Tunnels
   - Select your tunnel → Public Hostnames → Add hostname
   - Set service URL to: `http://api:8000` (internal container name)

### Option 3: Manual Container (Legacy)

For existing deployments, you can still use manual containers, but the compose approach is recommended.

## 🧪 Testing

Once configured, test your API:

```bash
# Health check
curl https://ai-kb-api.yourdomain.com/health

# API documentation
curl https://ai-kb-api.yourdomain.com/docs

# Search endpoint
curl -X POST https://ai-kb-api.yourdomain.com/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "max_results": 1}'
```

## 🔒 Security Recommendations

1. **Add Access Policies** in Cloudflare Zero Trust:
   - Restrict access by email, IP, or other criteria
   - Go to **Access** → **Applications** → **Add an application**

2. **Rate Limiting**: Consider adding rate limiting rules in Cloudflare

3. **API Keys**: Add authentication to your FastAPI app if needed

## 📊 Updated Configuration

### Registry Compose Deployment:
- **API Internal URL**: `http://api:8000` (within `ai-kb-network`)
- **API Container**: `ai-kb-api`  
- **Cloudflared Container**: `ai-kb-cloudflared`
- **Network**: `ai-kb-network` (internal only)
- **External Access**: Via Cloudflare Tunnel only
- **Profiles**: Use `--profile tunnel` to enable tunnel service

### Deployment Commands:
```bash
# Production with tunnel
docker-compose -f docker-compose.from-registry.yml --profile tunnel up -d

# Local development (no tunnel)  
docker-compose -f docker-compose.from-registry.yml up -d
```

## 🔍 Troubleshooting

If the tunnel doesn't work:

1. **Check container connectivity**:
   ```bash
   # From any container on the apps network
   docker run --rm --network apps nicolaka/netshoot curl http://ai-kb-api:8000/health
   ```

2. **Check cloudflared logs**:
   ```bash
   docker logs cloudflared
   ```

3. **Verify API health**:
   ```bash
   docker exec ai-kb-api curl http://localhost:8000/health
   ```

## 📝 Notes

- The API is already accessible locally on port 8001 (`http://100.106.229.15:8001`)
- Cloudflare Tunnel will provide HTTPS access with your custom domain
- The tunnel automatically handles SSL/TLS termination
