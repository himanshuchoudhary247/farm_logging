#!/bin/bash

# React Loop Skills - Local Deployment Script
# This script sets up and runs the local server with SQLite database

echo "🚀 React Loop Skills Local Deployment"
echo "======================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Node.js version
echo "📋 Checking prerequisites..."
if ! command -v node &> /dev/null; then
    echo "${RED}❌ Node.js is not installed${NC}"
    echo "Please install Node.js 18+ from https://nodejs.org/"
    exit 1
fi

NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "${RED}❌ Node.js version 18+ required, found $(node -v)${NC}"
    exit 1
fi

echo "${GREEN}✅ Node.js $(node -v)${NC}"

# Check npm
if ! command -v npm &> /dev/null; then
    echo "${RED}❌ npm is not installed${NC}"
    exit 1
fi

echo "${GREEN}✅ npm $(npm -v)${NC}"
echo ""

# Create data directory
echo "📁 Setting up directories..."
mkdir -p data
mkdir -p logs
echo "${GREEN}✅ Directories created${NC}"
echo ""

# Install dependencies
echo "📦 Installing dependencies..."
if [ ! -d "node_modules" ]; then
    npm install
    if [ $? -ne 0 ]; then
        echo "${RED}❌ Failed to install dependencies${NC}"
        exit 1
    fi
    echo "${GREEN}✅ Dependencies installed${NC}"
else
    echo "${YELLOW}⚠️  Dependencies already installed${NC}"
fi
echo ""

# Build TypeScript
echo "🔨 Building TypeScript..."
npm run build
if [ $? -ne 0 ]; then
    echo "${RED}❌ Build failed${NC}"
    exit 1
fi
echo "${GREEN}✅ Build successful${NC}"
echo ""

# Seed database
echo "🌱 Seeding database..."
npm run seed
if [ $? -ne 0 ]; then
    echo "${RED}❌ Database seeding failed${NC}"
    exit 1
fi
echo "${GREEN}✅ Database seeded${NC}"
echo ""

# Start server
echo "🎯 Starting server..."
echo ""
echo "${GREEN}Server will start on http://localhost:3001${NC}"
echo ""
echo "Test commands:"
echo "  curl http://localhost:3001/health"
echo "  curl http://localhost:3001/skills"
echo "  curl http://localhost:3001/farmers/farmer_001"
echo ""
echo "Press Ctrl+C to stop"
echo ""

npm start
