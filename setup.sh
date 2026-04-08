#!/bin/bash

# Quick Start Script for Reliable FTP Dashboard

echo
echo "========================================"
echo "  Reliable FTP Dashboard - Quick Start"
echo "========================================"
echo

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

echo "Installing dependencies..."
pip3 install -r requirements_dashboard.txt

echo
echo "========================================"
echo "  Setup Complete!"
echo "========================================"
echo
echo "To start the system:"
echo
echo "Terminal 1 - Start FTP Server:"
echo "  python3 server.py"
echo
echo "Terminal 2 - Start Dashboard:"
echo "  python3 dashboard.py"
echo
echo "Then open your browser to: http://localhost:5000"
echo
