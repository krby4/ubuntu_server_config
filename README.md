# Ubuntu Server Configuration Script
## Overview
This script automates the setup of Ubuntu servers in three different use cases:
- Boundary servers (Caddy reverse proxy setup, optional vpn setup)
- Compute environments (Development tools, flask website, wiki.js setup)
- Game servers (Minecraft, Valheim, Palworld, Windrose)

It standardizes directory structure, installs required software, and configures services automatically. Must be ran as sudo

Must be run with 'sudo'

Requires krby4_monitoring to work with --monitoring

## Usage

### Global Usage
```bash
sudo python3 ubuntu_server_config.py <mode> [options]
```
### Global Options
--monitoring Optionally installs a monitoring script and sets up the systemd timer to run the script as a service every 5 minutes
--dir-group Optionally adds a known group to directory access instead of just the user
--domain-name Optionally change the domain name from "2l2q.net" to one of your choosing. Used in every mode in settings
-l --log Optionally output to a log file
### Boundary Mode
--vpn Optionally installs Tailscale VPN. Setup requires user input, so setup is skipped
### Compute Mode
--wiki-name Optionally change the name of your wiki
### Game Mode
-g --game Name of the game you want to install in a list. Options are minecraft, valheim, palworld, windrose, all. Separated by spaces
-w --world-name Optionally change the name of the world from 2l2q.net
-s --seed Optionally add a seed number for minecraft
-m --memory Optionally change memory for container from 4G
### Example usage
Boundary
```bash
sudo python3 ubuntu_server_config.py boundary --vpn --domain-name test.domain
sudo python3 ubuntu_server_config.py boundary
```
Compute
```bash
sudo python3 ubuntu_server_config.py compute --domain-name test.domain --monitoring --wiki-name mywiki
sudo python3 ubuntu_server_config.py compute
```
Game
```bash
sudo python3 ubuntu_server_config.py game -g "minecraft"
sudo python3 ubuntu_server_config.py game -g "all" --monitoring
```
## How to Test
Requirements:
- Ubuntu server (only tested on 24.04)
- Python3
- Sudo Access
- Internet access
Optional:
- Clean VM's to test on. I used Multipass: https://canonical.com/multipass
Method:
- Copy script and config folder to server to the same location, then run with sudo
- For ease, I have included a multipass script that will create 3 vm's and run the script for each mode on a separate VM with all of the options besides log present
#### Validation
Check to see if homepage or wiki are running with
- Homepage: curl http://<vm-ip>:5000
- Wiki curl http://<vm-ip>:3000
Check to see if UFW enabled with 
- sudo ufw status
Check to see if docker containers are running
- docker stats
## Directory Structure
All services are installed under /srv/[mode]/
Examples:
- /srv/game/minecraft
- /srv/compute/homepage
- /srv/boundary/caddy
## Monitoring
If --monitoring is used, the script will copy the contents of /config/pylogger to the computer, enable systemd timers for logging metrics, and enable automatic log cleanup
This is the only part of the script that will actually install something with pip, as it uses the psutil module to gather cpu usage, disk usage, memory usage, and bytes recieved since the computer was turned on. This was written in 2025, and has tons of room for improvement
## Final notes
- Services assume default ports, it might overwrite something on an existing service
- Docker install is a fatal error
- Some services take a while to start up. My tests took around 10 minutes or more when installing all games
- Game servers will likely not be plug and play, as things like network firewall rules are likely required