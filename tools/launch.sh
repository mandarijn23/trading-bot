#!/bin/bash
# Trading Bot Quick Launcher
# Starts bot and dashboard in separate terminals or background processes

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  🤖 TRADING BOT LAUNCHER${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ .env file not found!${NC}"
    echo -e "Run: ${YELLOW}python setup.py${NC}"
    exit 1
fi

# Validate configuration
echo -e "${BLUE}Validating configuration...${NC}"
python cli.py validate-config

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Configuration validation failed!${NC}"
    exit 1
fi

echo -e "\n${GREEN}✅ Configuration valid${NC}\n"

# Menu
echo -e "${BLUE}Choose how to run:${NC}"
echo "  1) Run bot only (stock_bot.py)"
echo "  2) Run dashboard only (dashboard.py)"  
echo "  3) Run both (in separate background processes)"
echo "  4) Run crypto bot (bot.py)"
echo "  5) Test Discord webhook"
echo ""
read -p "Enter choice [1-5]: " choice

case $choice in
    1)
        echo -e "\n${YELLOW}Starting stock bot...${NC}\n"
        python stock_bot.py
        ;;
    2)
        echo -e "\n${YELLOW}Starting dashboard...${NC}\n"
        python dashboard.py
        ;;
    3)
        echo -e "\n${YELLOW}Starting both bot and dashboard...${NC}\n"
        
        # Check if tmux is available
        if command -v tmux &> /dev/null; then
            echo -e "${GREEN}Using tmux for split windows${NC}\n"
            
            # Create new session
            tmux new-session -d -s trading -x 200 -y 50
            
            # Create two windows
            tmux new-window -t trading -n "stock-bot"
            tmux new-window -t trading -n "dashboard"
            
            # Run bot in first window
            tmux send-keys -t trading:stock-bot "python stock_bot.py" Enter
            sleep 2
            
            # Run dashboard in second window
            tmux send-keys -t trading:dashboard "python dashboard.py" Enter
            
            # Attach to session
            echo -e "${GREEN}✅ Created tmux session 'trading'${NC}"
            echo -e "${GREEN}Attaching to session...${NC}\n"
            sleep 1
            tmux attach -t trading
        else
            # Fallback: Run in background
            echo -e "${YELLOW}tmux not found, running in background${NC}\n"
            
            # Start bot in background
            nohup python stock_bot.py > stock_bot.log 2>&1 &
            BOT_PID=$!
            echo -e "${GREEN}✅ Stock bot started (PID: $BOT_PID)${NC}"
            echo -e "   Logs: ${YELLOW}tail -f stock_bot.log${NC}"
            
            sleep 2
            
            # Start dashboard in background
            nohup python dashboard.py > dashboard.log 2>&1 &
            DASH_PID=$!
            echo -e "${GREEN}✅ Dashboard started (PID: $DASH_PID)${NC}"
            echo -e "   Logs: ${YELLOW}tail -f dashboard.log${NC}"
            
            echo -e "\n${GREEN}Both processes running in background${NC}"
            echo -e "Stop: ${YELLOW}kill $BOT_PID $DASH_PID${NC}"
            echo ""
        fi
        ;;
    4)
        echo -e "\n${YELLOW}Starting crypto bot (Binance)...${NC}\n"
        python bot.py
        ;;
    5)
        echo -e "\n${YELLOW}Testing Discord webhook...${NC}\n"
        python cli.py test-discord
        ;;
    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac
