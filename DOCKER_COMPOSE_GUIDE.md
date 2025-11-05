# Docker Compose Files Guide

This project provides multiple Docker Compose configurations for different use cases:

## 📁 Available Files

### `docker-compose.yml` (Default - Local Builds)
- **Purpose**: Development and testing with local builds
- **Usage**: `docker-compose up -d --build`
- **Images**: Builds locally from `./services/*/Dockerfile`
- **Best for**: Local development, testing changes

### `docker-compose-from-registry.yml` (Production)
- **Purpose**: Production deployment with pre-built images
- **Usage**: `docker-compose -f docker-compose-from-registry.yml up -d`
- **Images**: Uses `ghcr.io/hasomerhacairhu/ai-knowledge-base/*:latest`
- **Best for**: Production, staging, quick deployment

### `docker-compose-local-builld.yml` (Explicit Local)
- **Purpose**: Explicit local builds (same as default)
- **Usage**: `docker-compose -f docker-compose-local-builld.yml up -d --build`
- **Images**: Builds locally (identical to default)
- **Best for**: When you want to be explicit about local builds

## 🚀 Quick Commands

```bash
# Production (fastest startup)
make up-registry

# Development (default)
make up

# Explicit local builds
make up-local

# Stop all (handles all compose files)
make down
```

## 🏗️ Image Sources

- **Registry Images**: Auto-built via GitHub Actions on every push to main
- **Local Images**: Built from source code in `./services/` directories
- **Platforms**: Registry images support both AMD64 and ARM64

## 📝 Notes

- Registry images are recommended for production as they're pre-tested
- Local builds allow for immediate testing of code changes
- All compose files use identical service configurations (only image source differs)