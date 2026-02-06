#!/bin/bash

# PUBG Discord Bot Setup Script
# This script helps you set up the bot for the first time

set -e

echo "=========================================="
echo "PUBG Discord Bot - Setup Script"
echo "=========================================="
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version
if [ $? -ne 0 ]; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

# Check if pip is available
echo "Checking pip..."
python3 -m pip --version
if [ $? -ne 0 ]; then
    echo "❌ pip is not installed. Please install pip."
    exit 1
fi

# Install dependencies
echo ""
echo "Installing dependencies..."
python3 -m pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ Failed to install dependencies."
    exit 1
fi

echo "✅ Dependencies installed successfully!"

# Create config.json if it doesn't exist
if [ ! -f "config.json" ]; then
    echo ""
    echo "Creating config.json..."
    cat > config.json << EOF
{
  "pubg_api_key": "YOUR_PUBG_API_KEY_HERE",
  "discord_token": "YOUR_DISCORD_BOT_TOKEN_HERE",
  "discord_channel_id": 123456789012345678,
  "check_interval_seconds": 150,
  "request_delay": 7.0,
  "max_retries": 3
}
EOF
    echo "✅ config.json created!"
    echo "⚠️  Please edit config.json with your API keys and channel ID."
else
    echo "ℹ️  config.json already exists, skipping creation."
fi

# Create players.txt if it doesn't exist
if [ ! -f "players.txt" ]; then
    echo ""
    echo "Creating players.txt..."
    cat > players.txt << EOF
# Add player names here (one per line)
# Format: PlayerName or PlayerName,platform
# Platforms: steam, psn, xbox, kakao, stadia, console
#
# Examples:
# PlayerName1
# PlayerName2,steam
# ConsolePlayer,xbox
EOF
    echo "✅ players.txt created!"
    echo "⚠️  Please edit players.txt to add the players you want to track."
else
    echo "ℹ️  players.txt already exists, skipping creation."
fi

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit config.json with your API keys"
echo "   - Get PUBG API key from: https://developer.pubg.com/"
echo "   - Get Discord token from: https://discord.com/developers/applications"
echo ""
echo "2. Edit players.txt to add player names to track"
echo ""
echo "3. Run the bot:"
echo "   python3 app.py"
echo ""
echo "For more information, see README.md"
echo ""