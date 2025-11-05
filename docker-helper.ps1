# Docker Compose Helper Script for Windows PowerShell
# This script helps you choose and run the appropriate Docker Compose configuration

Write-Host "🐳 AI Knowledge Base - Docker Compose Helper" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Available deployment options:"
Write-Host "1. 🏭 Production (Registry Images) - Fast startup, pre-built images" -ForegroundColor Green
Write-Host "2. 🛠️  Development (Local Builds) - Build from source, test changes" -ForegroundColor Yellow
Write-Host "3. 📦 Explicit Local - Same as development, explicit file" -ForegroundColor Blue
Write-Host "4. ❓ Show status of running containers" -ForegroundColor Magenta
Write-Host "5. 🛑 Stop all services" -ForegroundColor Red
Write-Host ""

$choice = Read-Host "Choose an option (1-5)"

switch ($choice) {
    "1" {
        Write-Host "🏭 Starting with registry images..." -ForegroundColor Green
        docker-compose -f docker-compose-from-registry.yml up -d
        Write-Host "✅ Services started! API available at http://localhost:8000" -ForegroundColor Green
    }
    "2" {
        Write-Host "🛠️ Building and starting with local builds..." -ForegroundColor Yellow
        docker-compose up -d --build
        Write-Host "✅ Services started! API available at http://localhost:8000" -ForegroundColor Green
    }
    "3" {
        Write-Host "📦 Building and starting with explicit local builds..." -ForegroundColor Blue
        docker-compose -f docker-compose-local-builld.yml up -d --build
        Write-Host "✅ Services started! API available at http://localhost:8000" -ForegroundColor Green
    }
    "4" {
        Write-Host "📊 Container Status:" -ForegroundColor Magenta
        docker ps --filter "name=ai-kb" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    }
    "5" {
        Write-Host "🛑 Stopping all services..." -ForegroundColor Red
        try { docker-compose down 2>$null } catch {}
        try { docker-compose -f docker-compose-from-registry.yml down 2>$null } catch {}
        try { docker-compose -f docker-compose-local-builld.yml down 2>$null } catch {}
        Write-Host "✅ All services stopped" -ForegroundColor Green
    }
    default {
        Write-Host "❌ Invalid option. Please run the script again." -ForegroundColor Red
        exit 1
    }
}