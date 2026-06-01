#!/bin/bash

echo -e "\e[1;32m"
cat << 'EOF'
   __________  __    ____  __________ __  _______
  / ____/ __ \/ /   / __ \/ ___/ ___// / / / ___/
 / /   / / / / /   / / / /\__ \\__ \/ / / /\__ \ 
/ /___/ /_/ / /___/ /_/ /___/ /__/ / /_/ /___/ / 
\____/\____/_____/\____//____/____/\____//____/  
EOF
echo -e "\e[0m"

echo -e "\e[1;37m  The Colossus is online. All systems operational.\e[0m"
echo -e "\e[0;90m  $(date '+%A, %d %B %Y — %H:%M:%S')\e[0m"
echo -e "\e[0;90m  Uptime:$(uptime -p | sed 's/up//')\e[0m"
echo ""
