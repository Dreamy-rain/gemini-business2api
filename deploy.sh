#!/bin/bash

# Gemini Business2API Deployment Script for Linux/macOS
# This script automates the initial deployment process

set -e  # Exit on error

echo "=========================================="
echo "Gemini Business2API Deployment Script"
echo "=========================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored messages
print_success() {
    echo -e "${GREEN}[SUCCESS] $1${NC}"
}

print_error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

print_info() {
    echo -e "${YELLOW}[INFO] $1${NC}"
}

print_step() {
    echo -e "${BLUE}[STEP] $1${NC}"
}

# Check if git is installed
if ! command -v git &> /dev/null; then
    print_error "Git is not installed. Please install git first."
    exit 1
fi

# Check if python3 is installed
if ! command -v python3 &> /dev/null; then
    print_error "Python3 is not installed. Please install Python 3.11+ first."
    exit 1
fi

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    print_error "npm is not installed. Please install Node.js and npm first."
    exit 1
fi

# Step 1: Build frontend
print_step "Step 1: Building frontend..."
if [ -d "frontend" ]; then
    cd frontend
    print_info "Installing frontend dependencies..."
    npm install
    print_info "Building frontend..."
    npm run build
    print_success "Frontend built successfully"
    cd ..
else
    print_error "Frontend directory not found. Are you in the project root?"
    exit 1
fi

# Step 2: Create virtual environment
print_step "Step 2: Setting up Python virtual environment..."
if [ -d ".venv" ]; then
    print_info "Virtual environment already exists, skipping creation"
else
    print_info "Creating virtual environment..."
    python3 -m venv .venv
    print_success "Virtual environment created"
fi

# Activate virtual environment
print_info "Activating virtual environment..."
source .venv/bin/activate

# Step 3: Install Python dependencies
print_step "Step 3: Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
print_success "Python dependencies installed"

# Step 4: Setup .env file
print_step "Step 4: Setting up configuration..."
if [ -f ".env" ]; then
    print_info ".env file already exists, skipping"
else
    if [ -f ".env.example" ]; then
        cp .env.example .env
        print_success ".env file created from .env.example"
    else
        print_error ".env.example not found"
        exit 1
    fi
fi

# Step 5: Show completion message
echo ""
echo "=========================================="
print_success "Deployment completed successfully!"
echo "=========================================="
echo ""
print_info "Next steps:"
echo ""
echo "  1. Edit .env file and set your ADMIN_KEY:"
echo "     ${BLUE}nano .env${NC}  or  ${BLUE}vim .env${NC}"
echo ""
echo "  2. Start the service:"
echo "     ${BLUE}python main.py${NC}"
echo ""
echo "  3. Access the admin panel:"
echo "     ${BLUE}http://localhost:7860/${NC}"
echo ""
print_info "Optional: To activate virtual environment later, run:"
echo "  ${BLUE}source .venv/bin/activate${NC}"
echo ""
