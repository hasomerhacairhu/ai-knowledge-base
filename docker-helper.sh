#!/bin/bash
# Docker Compose Helper Script
# This script helps you choose and run the appropriate Docker Compose configuration

set -e

echo "🐳 AI Knowledge Base - Docker Compose Helper"
echo "============================================="
echo
echo "Available deployment options:"
echo "1. 🏭 Production (Registry Images) - Fast startup, pre-built images"
echo "2. 🛠️  Development (Local Builds) - Build from source, test changes"
echo "3. 📦 Explicit Local - Same as development, explicit file"
echo "4. ❓ Show status of running containers"
echo "5. 🛑 Stop all services"
echo

read -p "Choose an option (1-5): " choice

case $choice in
    1)
        echo "🏭 Starting with registry images..."
        docker-compose -f docker-compose-from-registry.yml up -d
        echo "✅ Services started! API available at http://localhost:8000"
        ;;
    2)
        echo "🛠️ Building and starting with local builds..."
        docker-compose up -d --build
        echo "✅ Services started! API available at http://localhost:8000"
        ;;
    3)
        echo "📦 Building and starting with explicit local builds..."
        docker-compose -f docker-compose-local-builld.yml up -d --build
        echo "✅ Services started! API available at http://localhost:8000"
        ;;
    4)
        echo "📊 Container Status:"
        docker ps --filter "name=ai-kb" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
        ;;
    5)
        echo "🛑 Stopping all services..."
        docker-compose down 2>/dev/null || true
        docker-compose -f docker-compose-from-registry.yml down 2>/dev/null || true
        docker-compose -f docker-compose-local-builld.yml down 2>/dev/null || true
        echo "✅ All services stopped"
        ;;
    *)
        echo "❌ Invalid option. Please run the script again."
        exit 1
        ;;
esac