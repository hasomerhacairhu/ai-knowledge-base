# Cloudflare Tunnel Setup for AI Knowledge Base API

## ✅ Completed Steps

1. **Network Configuration**: The API container (`ai-kb-api`) is now connected to both:
   - `ai-knowledge-base-ingest_ai-kb-network` (internal network with PostgreSQL)
   - `apps` (shared network with cloudflared)

2. **Container Status**: 
   - API is running and healthy
   - Accessible internally at `http://ai-kb-api:8000`

## 🔧 Next Steps: Configure Cloudflare Tunnel

Your cloudflared container is running with a tunnel token. To expose the API through Cloudflare Tunnel, you need to:

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

### Option 2: Via Configuration File

If you prefer to manage via config file, create a config on the host:

1. **Create config file**:
   ```bash
   ssh root@100.106.229.15
   mkdir -p /root/cloudflared
   cat > /root/cloudflared/config.yml << 'EOF'
   tunnel: <your-tunnel-id>
   credentials-file: /etc/cloudflared/credentials.json

   ingress:
     - hostname: ai-kb-api.yourdomain.com
       service: http://ai-kb-api:8000
     - service: http_status:404
   EOF
   ```

2. **Update cloudflared container** to use the config:
   ```bash
   docker stop cloudflared
   docker rm cloudflared
   
   docker run -d \
     --name cloudflared \
     --network apps \
     --restart unless-stopped \
     -v /root/cloudflared:/etc/cloudflared \
     cloudflare/cloudflared:latest \
     tunnel --config /etc/cloudflared/config.yml run
   ```

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

## 📊 Current Configuration

- **API Internal URL**: `http://ai-kb-api:8000`
- **API Container**: `ai-kb-api`
- **Cloudflared Container**: `cloudflared`
- **Shared Network**: `apps`
- **API Port**: 8000 (also exposed on host as 8001)

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
