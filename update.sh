#!/bin/bash

# Gemini Business2API Update Script for Linux/macOS
# This script updates the project to the latest version

set -e  # Exit on error

echo "=========================================="
echo "Gemini Business2API Update Script"
echo "=========================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# Step 1: Backup current .env file
print_info "Backing up .env file..."
if [ -f ".env" ]; then
    cp .env .env.backup
    print_success ".env backed up to .env.backup"
else
    print_info "No .env file found, skipping backup"
fi

# Step 2: Pull latest code from git
print_info "Pulling latest code from git..."
git fetch origin
git pull origin main || git pull origin master
print_success "Code updated successfully"

# Step 3: Restore .env file
if [ -f ".env.backup" ]; then
    print_info "Restoring .env file..."
    mv .env.backup .env
    print_success ".env restored"
fi

# Step 4: Update Python dependencies
print_info "Updating Python dependencies..."
if [ -d ".venv" ]; then
    print_info "Virtual environment detected, activating..."
    source .venv/bin/activate
fi

pip install -r requirements.txt --upgrade
print_success "Python dependencies updated"

# Step 5: Update frontend dependencies
if [ -d "frontend" ]; then
    print_info "Updating frontend dependencies..."
    cd frontend

    # Check if npm is installed
    if command -v npm &> /dev/null; then
        npm install
        npm run build
        print_success "Frontend dependencies updated and built"
    else
        print_error "npm is not installed. Skipping frontend update."
    fi

    cd ..
fi

# Step 6: Show completion message
echo ""
echo "=========================================="
print_success "Update completed successfully!"
echo "=========================================="
echo ""
print_info "To restart the service, run:"
echo "  python main.py"
echo ""
print_info "Or if using systemd:"
echo "  sudo systemctl restart gemini-business2api"
echo ""
