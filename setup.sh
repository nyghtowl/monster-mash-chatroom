#!/usr/bin/env bash
#
# setup.sh - Initial setup script for Monster Mash Chatroom
#
set -e

echo "🎃 Setting up Monster Mash Chatroom..."

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not found. Please install Python 3.10+."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "✓ Found Python $PYTHON_VERSION"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔮 Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
echo "📚 Installing dependencies..."
pip install --upgrade pip > /dev/null
pip install -e .[dev]

# Copy .env.example if .env doesn't exist
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env from template..."
    cp .env.example .env
    echo "✓ Created .env file"
    echo ""
    echo "📝 IMPORTANT: Edit .env to configure your setup!"
    echo "   - Keep DEMO_MODE=true for testing without LLM APIs"
    echo "   - Or set DEMO_MODE=false and add 1-5 LLM API keys:"
    echo "     • OPENAI_API_KEY for GPT models"
    echo "     • ANTHROPIC_API_KEY for Claude models"
    echo "     • Or install Ollama (https://ollama.ai) for free local models"
    echo ""
else
    echo "✓ .env file already exists"
fi

# Check if Docker is available (optional)
if command -v docker &> /dev/null; then
    echo "✓ Docker found (optional, for Kafka message bus)"
else
    echo "ℹ️  Docker not found - will use in-memory message bus (single-machine mode)"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "🚀 Quick Start:"
echo "   ./run.sh --with-workers    # Start everything"
echo "   ./panic.sh                 # Stop everything"
echo ""
echo "📖 Visit http://localhost:8000 after starting"
echo ""
