#!/bin/bash

# Quick Start Script for Face Recognition Web App (Mac/Linux)

echo ""
echo "===================================================="
echo "   FACE RECOGNITION WEB APP - QUICK START"
echo "===================================================="
echo ""

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "Virtual environment created!"
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Install requirements
echo ""
echo "Installing packages (this may take a few minutes)..."
pip install -r requirements_web.txt

# Run the app
echo ""
echo "===================================================="
echo "   STARTING APPLICATION..."
echo "===================================================="
echo ""
echo "Open your browser and go to:"
echo "   http://localhost:5000"
echo ""
echo "Press Ctrl+C to stop the app"
echo "===================================================="
echo ""

python app.py
