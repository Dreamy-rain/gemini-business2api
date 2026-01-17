#!/bin/bash

# Gemini Business2API Unified Setup Script
# This script handles both initial deployment and updates
# Usage:
#   ./setup.sh          - Initial deployment
#   ./setup.sh --update - Update existing installation

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

# Determine mode (initial deployment or update)
UPDATE_MODE=false
if [[ "$1" == "--update" ]]; then
    UPDATE_MODE=true
    print_info "Running in UPDATE mode"
else
    print_info "Running in INITIAL DEPLOYMENT mode"
fi
echo ""

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

# Step 1: Backup .env file (update mode only)
if [ "$UPDATE_MODE" = true ]; then
    print_step "Step 1: Backing up configuration..."
    if [ -f ".env" ]; then
        cp .env .env.backup
        print_success ".env backed up to .env.backup"
    else
        print_info "No .env file found, skipping backup"
    fi
    echo ""
fi

# Step 2: Pull latest code from git (both modes)
print_step "Step 2: Syncing code from repository..."
print_info "Fetching latest changes..."
git fetch origin

print_info "Pulling latest code..."
if git pull origin main 2>/dev/null || git pull origin master 2>/dev/null; then
    print_success "Code synchronized successfully"
else
    print_info "No remote changes to pull (this is normal for initial deployment)"
fi
echo ""

# Step 3: Restore .env file (update mode only)
if [ "$UPDATE_MODE" = true ] && [ -f ".env.backup" ]; then
    print_step "Step 3: Restoring configuration..."
    mv .env.backup .env
    print_success ".env restored"
    echo ""
fi

# Step 4: Setup .env file (initial deployment only)
if [ "$UPDATE_MODE" = false ]; then
    print_step "Step 3: Setting up configuration..."
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
    echo ""
fi

# Step 5: Setup Python virtual environment
print_step "Step 4: Setting up Python environment..."
if [ -d ".venv" ]; then
    print_info "Virtual environment already exists"
else
    print_info "Creating virtual environment..."
    python3 -m venv .venv
    print_success "Virtual environment created"
fi

print_info "Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
print_info "Upgrading pip..."
pip install --upgrade pip --quiet
print_success "Pip upgraded"
echo ""

# Step 6: Install/Update Python dependencies
print_step "Step 5: Installing Python dependencies..."
if [ "$UPDATE_MODE" = true ]; then
    pip install -r requirements.txt --upgrade
    print_success "Python dependencies updated"
else
    pip install -r requirements.txt
    print_success "Python dependencies installed"
fi
echo ""

# Step 7: Setup frontend
print_step "Step 6: Setting up frontend..."
if [ -d "frontend" ]; then
    cd frontend

    # Check if npm is installed
    if command -v npm &> /dev/null; then
        print_info "Installing frontend dependencies..."
        npm install

        print_info "Building frontend..."
        npm run build
        print_success "Frontend built successfully"
    else
        if [ "$UPDATE_MODE" = false ]; then
            print_error "npm is not installed. Please install Node.js and npm first."
            cd ..
            exit 1
        else
            print_error "npm is not installed. Skipping frontend update."
        fi
    fi

    cd ..
else
    print_error "Frontend directory not found. Are you in the project root?"
    exit 1
fi
echo ""

# Step 8: Show completion message
echo "=========================================="
print_success "Setup completed successfully!"
echo "=========================================="
echo ""

if [ "$UPDATE_MODE" = true ]; then
    print_info "Update completed. To restart the service:"
    echo ""
    echo "  ${BLUE}python main.py${NC}"
    echo ""
    print_info "Or if using systemd:"
    echo "  ${BLUE}sudo systemctl restart gemini-business2api${NC}"
else
    print_info "Initial deployment completed. Next steps:"
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
    print_info "To activate virtual environment later, run:"
    echo "  ${BLUE}source .venv/bin/activate${NC}"
fi
echo ""
