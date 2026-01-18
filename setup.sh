#!/bin/bash

# Gemini Business2API Setup Script
# Handles both installation and updates automatically
# Usage: ./setup.sh

set -e  # Exit on error

echo "=========================================="
echo "Gemini Business2API Setup Script"
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
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}→ $1${NC}"
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

# Step 1: Pull latest code from git
print_step "Step 1: Syncing code from repository..."
print_info "Fetching latest changes..."
git fetch origin

print_info "Pulling latest code..."
if git pull origin main 2>/dev/null || git pull origin master 2>/dev/null; then
    print_success "Code synchronized successfully"
else
    print_info "No remote changes to pull"
fi
echo ""

# Step 2: Setup .env file if it doesn't exist
print_step "Step 2: Checking configuration..."
if [ -f ".env" ]; then
    print_info ".env file exists"
else
    if [ -f ".env.example" ]; then
        cp .env.example .env
        print_success ".env file created from .env.example"
        print_info "Please edit .env and configure your ADMIN_KEY"
    else
        print_error ".env.example not found"
        exit 1
    fi
fi
echo ""

# Step 3: Setup Python virtual environment
print_step "Step 3: Setting up Python environment..."
if [ -d ".venv" ]; then
    print_info "Virtual environment already exists"
else
    print_info "Creating virtual environment..."
    python3 -m venv .venv
    print_success "Virtual environment created"
fi

print_info "Activating virtual environment..."
source .venv/bin/activate

print_info "Upgrading pip..."
pip install --upgrade pip --quiet
print_success "Pip upgraded"
echo ""

# Step 4: Install/Update Python dependencies
print_step "Step 4: Installing Python dependencies..."
pip install -r requirements.txt --upgrade
print_success "Python dependencies installed"
echo ""

# Step 5: Setup frontend
print_step "Step 5: Setting up frontend..."
if [ -d "frontend" ]; then
    cd frontend

    # Check if npm is installed
    if command -v npm &> /dev/null; then
        print_info "Installing dependencies..."
        npm install

        print_info "Building frontend..."
        npm run build
        print_success "Frontend built successfully"
    else
        print_error "npm is not installed. Please install Node.js and npm first."
        cd ..
        exit 1
    fi

    cd ..
else
    print_error "Frontend directory not found. Are you in the project root?"
    exit 1
fi
echo ""

# Step 6: Show completion message
echo "=========================================="
print_success "Setup completed successfully!"
echo "=========================================="
echo ""

if [ -f ".env" ]; then
    print_info "Next steps:"
    echo ""
    echo "  1. Edit .env file if needed:"
    echo "     ${BLUE}nano .env${NC}  or  ${BLUE}vim .env${NC}"
    echo ""
    echo "  2. Start the service:"
    echo "     ${BLUE}python main.py${NC}"
    echo ""
    echo "  3. Access the admin panel:"
    echo "     ${BLUE}http://localhost:7860/${NC}"
    echo ""
    print_info "To activate virtual environment later, run:"
    echo "  ${BLUE}source .venv/bin/activate${NC}"
fi
echo ""
