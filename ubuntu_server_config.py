#!/usr/bin/env python3
import argparse
import subprocess
import pathlib
import os
import sys
import logging
import datetime
import pwd
import grp

# =================================
# Argument parsing
# =================================
def parse_args():
    parser = argparse.ArgumentParser(description="Multi-mode Ubuntu server configuration script")
    subparsers = parser.add_subparsers(dest="mode", required=True, help="boundary, compute, game")
    # boundary options
    boundary_parser = subparsers.add_parser("boundary", help="Set up a boundary server")
    boundary_parser.add_argument("--vpn", action="store_true", help="Install the Tailscale VPN client")
    # compute options
    compute_parser = subparsers.add_parser("compute",help="Set up a compute server")
    compute_parser.add_argument("--wiki-name", help="The name you want for your wiki, defaults to iwiki", default="iwiki")
    # game options
    game_parser = subparsers.add_parser("game", help="Set up a game server")
    game_parser.add_argument("-g","--game",help="Game to install, Minecraft, Palworld, Windrose, Valheim, or all",nargs="+",choices=["minecraft", "palworld", "windrose", "valheim", "all"] )
    game_parser.add_argument("-w","--world-name", help="World name of servers, defaults to 2l2q.net", default="2l2q.net")
    game_parser.add_argument("-s","--seed",help="Optionally add a seed number", default="8468982844759573060")
    game_parser.add_argument("-m","--memory",help="Amount of memory to dedicate to the host, defaults to 4G",default="4G")
    
    # shared parsers
    for sub in [boundary_parser,compute_parser,game_parser]:
        sub.add_argument("--monitoring",action="store_true",help="Enable a monitoring script through systemd")
        sub.add_argument("--dir-group", help="Optionally add a group to directory permissions")
        sub.add_argument("--domain-name", help="Domain name of your servers")
        sub.add_argument("-v", "--verbose", action="store_true")
        sub.add_argument("-l", "--log", nargs="?", const="AUTO", default=None)
    return parser.parse_args()

# =================================
# Logging
# =================================
def generate_log_name(args):
    # generates log name if you do not specify one in args
    date = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{args.mode}_{date}.log"

def make_logfile_name(args):
    # calls generate log name if no log name is given
    if args.log == "AUTO":
        return generate_log_name(args)
    return args.log

def setup_logger(verbose=False, logfile=None):
    # sets up the logger to use for the script including a file handler
    logger = logging.getLogger(__name__)
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG)

    level = logging.DEBUG if verbose else logging.INFO
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
        
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if logfile:
        file_handler = logging.FileHandler(logfile)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

# ==================================================================
# Helpers
# ==================================================================

def verify_root(logger):
    # exit script if not being run as root
    if os.geteuid() != 0:
        logger.error("Run this script with sudo")
        sys.exit(1)

def get_user():
    # returns the user that ran the script
    return os.getenv("SUDO_USER") or os.getenv("USER")

def create_dir(path, user, group=None):
    # creates dir and assigns ownership
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)

    uid = pwd.getpwnam(user).pw_uid

    if group:
        gid = grp.getgrnam(group).gr_gid
    else:
        gid = pwd.getpwnam(user).pw_gid

    os.chown(path,uid,gid)
# =================================
# For every mode
# =================================
def make_std_directories(args, user, logger):
    # Makes standard directories and sets permissions with user variable
    logger.info("Creating myServices, configs, logs, and backup under {}")
    base = pathlib.Path("/srv") / args.mode
    logger.info(f"Creating myServices, configs, logs, and backup under {base}")
    create_dir(base / "myServices", user, args.dir_group)
    create_dir(base / "configs", user, args.dir_group)
    create_dir(base / "logs", user, args.dir_group)
    create_dir(base / "backups", user, args.dir_group)
    
    user_home = pathlib.Path(pwd.getpwnam(user).pw_dir)
    logger.info(f"Creating code under {user_home}")
    create_dir(user_home / "code", user)

def run_command(command, logger, capture_output=False, cwd=None, fatal=False):
    # shell for subprocess to build it out easier than having to manually do each one
    logger.info("Running command: %s", " ".join(str(part) for part in command))
    result = subprocess.run(command,text=True,capture_output=capture_output, cwd=cwd)

    if capture_output and result.stdout:
        logger.debug(f"Command output: {result.stdout.strip()}")
    if result.returncode !=0:
        logger.error(f"Command failed with exit code{result.returncode}")
        if fatal:
            sys.exit(result.returncode)
        if result.stderr:
            logger.error(f"Error output {result.stderr.strip()}")
    return result

def install_docker(logger):
    # installs docker according to https://docs.docker.com/engine/install/ubuntu/
    # uninstall dependencies, will get reinstalled later
    logger.info("Begining install docker")
    logger.info("Uninstalling packages")
    dpkg_result = run_command(
        ["dpkg", "--get-selections", "docker.io",
        "docker-compose", "docker-compose-v2",
        "docker-doc", "podman-docker", "containerd",
        "runc"], logger,
        capture_output=True
    )
    # packages to uninstall, only if installed
    packages = []
    for line in dpkg_result.stdout.splitlines():
        if line.strip():
            packages.append(line.split()[0])
    if packages:
        logger.info(f"Removing old docker packages: {packages}")
        run_command(["apt", "remove", "-y", *packages],logger)
    else:
        logger.info("No old Docker packages found")
    # actually install docker
    logger.info("Updating and installing docker ca-cert")
    run_command(["apt", "update"], logger)
    run_command(["apt", "install", "-y", "ca-certificates", "curl"],logger, fatal=True)
    run_command(["install", "-m", "0755", "-d", "/etc/apt/keyrings"],logger, fatal=True)
    run_command(
        ["curl", "-fsSL",
        "https://download.docker.com/linux/ubuntu/gpg",
        "-o", "/etc/apt/keyrings/docker.asc"],logger, fatal=True)
    run_command(["chmod", "a+r", "/etc/apt/keyrings/docker.asc"], logger)
    # set up repo
    arch = run_command(
        ["dpkg", "--print-architecture"],logger,
        capture_output=True, fatal=True
    ).stdout.strip()
    # get ubuntu codename from os-release
    codename = None
    with open("/etc/os-release") as f:
        for line in f:
            if line.startswith("VERSION_CODENAME="):
                codename = line.strip().split("=")[1]
                break
    content = f"""Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: {codename}
Components: stable
Architectures: {arch}
Signed-By: /etc/apt/keyrings/docker.asc
"""
    pathlib.Path("/etc/apt/sources.list.d/docker.sources").write_text(content)
    run_command(["apt", "update"],logger)
    # add docker stuff
    logger.info("Installing docker packages")
    run_command([
        "apt", "install", "-y", "docker-ce", "docker-ce-cli",
        "containerd.io", "docker-buildx-plugin", "docker-compose-plugin"
    ],logger, fatal=True,capture_output=True)
    logger.info("Done installing docker")
    logger.info("Configuring Docker access")
    user = get_user()
    run_command(["groupadd","docker"], logger)
    run_command(["usermod","-aG","docker",user],logger)
    logger.info("Done configuring docker access")

def run_ufw(service, logger, proto="tcp"):
    # allows the service in ufw
    if isinstance(service, int):
        # port number
        cmd = ["ufw", "allow", f"{service}/{proto}"]
    else:
        # service name like "SSH"
        cmd = ["ufw", "allow", service]
    return run_command(cmd, logger)

def configure_ufw(logger):
    logger.info("Installing UFW and enabling SSH")
    # installs ufw and enables ssh
    run_command(["apt","install","-y","ufw"],logger,fatal=True)
    # default to deny all incoming
    run_command(["ufw", "default", "deny", "incoming"], logger)
    run_command(["ufw", "default", "allow", "outgoing"], logger)
    run_ufw("SSH",logger)
    run_ufw(22,logger)
    run_command(["ufw","--force","enable"],logger,fatal=True)
    logger.info("UFW enabled")

def configure_common(args, logger):
    user = get_user()
    make_std_directories(args,user,logger)
    configure_ufw(logger)
    install_docker(logger)
    if args.monitoring:
        install_monitoring(args,logger)

def install_monitoring(args,logger):
    # copies the metrics script and sets up systemd timer
    logger.info("Installing monitoring script and enabling systemd timer")
    # copy files over
    cwd = pathlib.Path(__file__).resolve().parent
    user = get_user()
    run_path = pathlib.Path("/srv") / args.mode / "monitoring"
    systemd_path = pathlib.Path("/etc/systemd/system")

    logger.info(f"Making {run_path} directory")
    create_dir(run_path,user,args.dir_group)

    template_path = cwd / "config" / "pylogger"
    logger_service_path = template_path / "pylogger.service"
    logger_timer_path = template_path / "pylogger.timer"
    cleanup_service_path = template_path / "pylogger-cleanup.service"
    cleanup_timer_path = template_path / "pylogger-cleanup.timer"
    pylogger_path = template_path / "pylogger.py"
    cleanup_path = template_path / "pylogger-cleanup.sh"
    logger.info("Copying services, timers, and scripts")
    run_command(["cp",str(logger_service_path),str(systemd_path / "pylogger.service")],logger)
    run_command(["cp",str(logger_timer_path),str(systemd_path / "pylogger.timer")],logger)
    run_command(["cp",str(cleanup_service_path),str(systemd_path / "pylogger-cleanup.service")],logger)
    run_command(["cp",str(cleanup_timer_path),str(systemd_path / "pylogger-cleanup.timer")],logger)
    run_command(["cp",str(pylogger_path),str(run_path / "pylogger.py")],logger)
    run_command(["cp",str(cleanup_path),str(run_path / "pylogger-cleanup.sh")],logger)
    logger.info("Done copying files")
    logger.info("Editing services and cleanup script")
    # edit the pylogger service
    with open(systemd_path / "pylogger.service", "r") as f:
        content = f.read()
    content = content.replace('{{user}}',user)
    content = content.replace('{{working_dir}}',str(run_path))
    pylogger_run_path = run_path / "pylogger.py"
    content = content.replace('{{exec_start}}',f'/usr/bin/python3 {pylogger_run_path}')

    with open(systemd_path / "pylogger.service", "w") as f:
        f.write(content)
    
    # edit the pylogger_cleanup service
    with open(systemd_path / "pylogger-cleanup.service","r") as f:
        content = f.read()
    content = content.replace('{{user}}',user)
    content = content.replace('{{working_dir}}',str(run_path))
    pylogger_cleanup_run_path = run_path / "pylogger-cleanup.sh"
    content = content.replace('{{exec_start}}',str(pylogger_cleanup_run_path))

    with open(systemd_path / "pylogger-cleanup.service", "w") as f:
        f.write(content)
    # edit the pylogger.py
    logger.info("Editing pylogger.py")
    with open(run_path / "pylogger.py","r") as f:
        content = f.read()
    log_path = run_path / "logs"
    content = content.replace('{{log_path}}',str(log_path))
    with open(run_path / "pylogger.py","w") as f:
        f.write(content)
    # edit the pylogger-cleanup.sh
    logger.info("Editing pylogger-cleanup.sh")
    with open(run_path / "pylogger-cleanup.sh", "r") as f:
        content = f.read()
    log_dir = run_path / "logs"
    content = content.replace('{{log_dir}}',str(log_dir))
    with open(run_path / "pylogger-cleanup.sh", "w") as f:
        f.write(content)
    logger.info("Creating log directory")
    create_dir(run_path / "logs", user, args.dir_group)
    logger.info("Done editing services and scripts")
    # enable systemd timers
    logger.info("Installing psutil")
    run_command(["apt","install","-y","python3-psutil"],logger)
    logger.info("Enabling timers")
    run_command(["systemctl","daemon-reload"],logger)
    result = run_command(["systemctl","enable","--now","pylogger.timer"],logger)
    if result.returncode != 0:
        logger.warning("pylogger not enabled")
    result = run_command(["systemctl","enable","--now","pylogger-cleanup.timer"],logger)
    if result.returncode != 0:
        logger.warning("pylogger-cleanup not enabled")
    logger.info("Done setting up monitoring")
    
    
# =================================
# For boundary mode
# =================================

def install_caddy(args, logger):
    # install caddy and drop a default caddyfile into /srv/boundary/caddy
    logger.info("Installing Caddy")
    run_command(["apt", "install", "-y", "caddy"], logger, fatal=True)
    user = get_user()
    logger.info("Creating caddy directory")
    caddy_dir = pathlib.Path("/srv") / args.mode / "caddy"
    create_dir(caddy_dir,user,args.dir_group)
    caddyfile_path = caddy_dir / "Caddyfile"
    logger.info(f"Creating caddy file to {caddyfile_path}")
    # make default caddy file
    with open(caddyfile_path,"w") as f:
        f.write("{\n")
        f.write(f"\temail {user}@{args.domain_name}\n")
        f.write("\tdebug\n")
        f.write("}\n\n")
        f.write(f"{args.domain_name} ")
        f.write("{\n")
        f.write('\trespond "Boundary server is online"\n')
        f.write("}\n")
    # start caddy as a service using the caddy file
    logger.info("Enabling caddy as a service with systemd")
    run_command(["cp", str(caddyfile_path), "/etc/caddy/Caddyfile"], logger, fatal=True)
    run_command(["caddy", "validate", "--config", "/etc/caddy/Caddyfile"], logger, fatal=True)
    run_command(["systemctl", "enable", "--now", "caddy"], logger, fatal=True)
    run_command(["systemctl", "reload", "caddy"], logger, fatal=True)
    logger.info("Done installing caddy")

def install_vpn(logger):
    # install tailscale VPN. It doesn't configure it because that requires an account
    logger.info("Installing Tailscale VPN client")
    result = run_command(["curl","-fsSL","https://tailscale.com/install.sh","-o","/tmp/tailscale-install.sh"],logger)
    if result.returncode == 0:
        result2 = run_command(["sh","/tmp/tailscale-install.sh"],logger)
        if result2.returncode == 0:
            logger.info("Done installing Tailscale")
        else:
            logger.warning("Couldn't install tailscale")
    else:
        logger.error("Couldn't download tailscale sh file, did not install tailscale")

# =================================
# For compute mode
# =================================

def install_python_git_buildessential(logger):
    # installs venv, pip, git, and the buildessential packages
    logger.info("Installing venv, pip, and git")
    run_command(["apt","update"],logger)
    run_command(["apt","install","-y","python3-venv","python3-pip","git","build-essential"],logger)
    logger.info("Done installing venv,pip, and git")

def configure_flask_page(args,logger):
    # Creates a default homepage using Flask
    name = args.domain_name
    logger.info(f"Setting up a default web page: Welcome to {name}")
    path = pathlib.Path("/srv") / args.mode / "homepage"
    user = get_user()
    logger.info("Creating directory for homepage")
    create_dir(path,user,args.dir_group)
    # create requirements.txt for flask
    logger.info("Creating requirements.txt")
    with open(path / "requirements.txt", "w") as f:
        f.write(f"flask\n")
    # create the app.py that will run a basic text webpage at 0.0.0.0:5000
    logger.info("Creating app.py")
    with open(path / "app.py","w") as f:
        f.write("from flask import Flask\n")
        f.write("app = Flask(__name__)\n")
        f.write('@app.route("/")\n')
        f.write("def home():\n")
        f.write(f'\treturn "Welcome to {name}!"\n')
        f.write('if __name__ == "__main__":\n')
        f.write('\tapp.run(host="0.0.0.0", port=5000)\n')
    # create the docker file
    logger.info("Creating Dockerfile")
    with open(path / "Dockerfile","w") as f:
        f.write("FROM python:3.12-slim\n")
        f.write("WORKDIR /app\n")
        f.write("COPY requirements.txt .\n")
        f.write("RUN pip install --no-cache-dir -r requirements.txt\n")
        f.write("COPY app.py .\n")
        f.write('CMD ["python","app.py"]\n')
    # create the dockercompose file
    logger.info("Creating compose.yaml")
    with open(path / "compose.yaml","w") as f:
        f.write("services:\n")
        f.write("  homepage:\n")
        f.write("    build: .\n")
        f.write("    container_name: compute_homepage\n")
        f.write("    ports:\n")
        f.write('      - "5000:5000"\n')
        f.write("    restart: unless-stopped\n")
    # create docker instance and run it as a service
    logger.info("Building and starting Flask docker container")
    result = run_command(["docker","compose","up","-d","--build"],logger,cwd=path)
    if result.returncode != 0:
        logger.warning("Docker compose failed to start the website")
    else:
        logger.info("Opening port 5000 in ufw")
        run_ufw(5000,logger)
        logger.info("Running the flask app on port 5000")

def configure_wiki(args,logger):
    # creates docker compose file and sets up docker container for a wiki.js wiki
    logger.info("Installing wiki.js and setting it up")
    path = pathlib.Path("/srv") / args.mode / "wiki"
    logger.info(f"Creating wiki directories at {path}")
    user = get_user()
    create_dir(path,user,args.dir_group)
    # create files
    logger.info(f"Creating compose.yaml at {path}")
    content = f"""services:
  db:
    image: postgres:15
    container_name: {args.wiki_name}_db
    environment:
      POSTGRES_DB: wiki
      POSTGRES_USER: wiki
      POSTGRES_PASSWORD: wikisecret
    volumes:
      - wiki_db_data:/var/lib/postgresql/data
    restart: unless-stopped

  wiki:
    image: ghcr.io/requarks/wiki:2
    container_name: {args.wiki_name}_app
    depends_on:
      - db
    environment:
      DB_TYPE: postgres
      DB_HOST: db
      DB_PORT: 5432
      DB_USER: wiki
      DB_PASS: wikisecret
      DB_NAME: wiki
    ports:
      - "3000:3000"
    restart: unless-stopped

volumes:
  wiki_db_data:"""
    
    with open(path / "compose.yaml", "w") as f:
        f.write(content)
    result = run_command(["docker","compose","up","-d","--build"],logger,cwd=path)
    if result.returncode != 0:
        logger.warning("Docker compose failed to start the wiki")
    else:
        logger.info("Opening port 3000 in ufw")
        run_ufw(3000,logger)
        logger.info("Running wiki.js on port 3000")


# =================================
# Game mode functions
# =================================
def install_steamdb(args,logger):
    logger.info("Installing steamdb")

def install_minecraft(args,logger):
    # creates docker compose file and creates and runs minecraft container on 25565
    logger.info("Installing Minecraft")
    logger.info("Creating the minecraft directory")
    path = pathlib.Path("/srv") / args.mode / "minecraft"
    user = get_user()
    create_dir(path,user,args.dir_group)
    logger.info("Creating the docker compose file")
    seed_line = f'      SEED: "{args.seed}"\n' if args.seed else ""
    content = f"""services:
  mc:
    image: itzg/minecraft-server
    environment:
      EULA: "true"
      MEMORY: "{args.memory}"
      LEVEL: "{args.world_name}"
{seed_line}
    ports:
      - "25565:25565"
    volumes:
      - data:/data
    stdin_open: true
    tty: true
    restart: unless-stopped
volumes:
  data:
"""
    with open (path / "compose.yaml", "w") as f:
        f.write(content)
    logger.info("Starting minecraft server")
    result = run_command(["docker","compose","up","-d"],logger,cwd=path)
    if result.returncode != 0:
        logger.warning("Docker compose failed to start minecraft")
    else:
        logger.info("Opening port 25565 in ufw")
        run_ufw(25565,logger)
        logger.info("Running minecraft on 25565")

def install_windrose(args,logger):
    # creates docker compose file and creates and runs windrose container on 7777
    logger.info("Installing Windrose")
    logger.info("Creating Windorose directory")
    path = pathlib.Path("/srv") / args.mode / "windrose"
    user = get_user()
    create_dir(path,user,args.dir_group)
    create_dir(path / "server-files",user,args.dir_group)
    logger.info("Creating the env file")
    content = f"""
PUID=1000
PGID=1000
UPDATE_ON_START=true
INVITE_CODE=123454321
SERVER_PORT=7777
USER_SELECTED_REGION=
SERVER_NAME={args.world_name}
SERVER_PASSWORD=CHANGE-ME
MAX_PLAYERS=10
P2P_PROXY_ADDRESS=127.0.0.1

# Direct Connections - cannot be used with P2P Proxy
USE_DIRECT_CONNECTION=false
DIRECT_CONNECTION_PROXY_ADDRESS=0.0.0.0

UE4SS_ENABLED=false

WINDROSE_PLUS_ENABLED=false

WINDROSE_PLUS_VERSION=
WINDROSE_PLUS_DASHBOARD_PORT=8780
WINDROSE_PLUS_RCON_PASSWORD=
"""
    with open(path / ".env","w") as f:
        f.write(content)
    
    logger.info("Creating the docker compose file")
    content = f"""services:
  windrose:
    image: indifferentbroccoli/windrose-server-docker:wine-staging
    platform: linux/amd64
    restart: unless-stopped
    container_name: windrose
    stop_grace_period: 30s
    network_mode: host
    security_opt:
      - seccomp:unconfined
    env_file:
      - .env
    volumes:
      - ./server-files:/home/steam/server-files
"""
    with open(path / "compose.yaml","w") as f:
        f.write(content)
    
    logger.info("Starting Windrose server")
    result = run_command(["docker","compose","up","-d"],logger,cwd=path)
    if result.returncode != 0:
        logger.warning("Docker compose failed to start Windrose")
    else:
        logger.info("Opening port 7777 in ufw")
        run_ufw(7777,logger)
        run_ufw(7777,logger,"udp")
        logger.info("Running Windrose on 7777")

def install_valheim(args,logger):
    # creates docker compose file and creates and runs valheim container on 9001
    logger.info("Installing Valheim")
    logger.info("Creating Valheim directory")
    path = pathlib.Path("/srv") / args.mode / "valheim"
    user = get_user()
    create_dir(path,user,args.dir_group)
    create_dir(path / "valheim-server", user, args.dir_group)
    create_dir(path / "valheim-server" / "config", user, args.dir_group)
    create_dir(path / "valheim-server" / "data", user, args.dir_group)
    logger.info("Creating the .env file")
    content = f"""PUID=1000
PGID=1000
TZ=America/Los_Angeles
SERVER_NAME={args.domain_name}
WORLD_NAME={args.world_name}
SERVER_PASS=CHANGE-ME
SERVER_PUBLIC=0
BACKUPS_MAX_AGE=30
"""
    with open(path / "valheim-server" / "valheim.env","w") as f:
        f.write(content)
    logger.info("Creating the Valheim compose file")
    content = f"""services:
  valheim:
    image: ghcr.io/community-valheim-tools/valheim-server
    cap_add:
      - sys_nice
    volumes:
      - ./valheim-server/config:/config
      - ./valheim-server/data:/opt/valheim
    ports:
      - "2456-2458:2456-2458/udp"
      - "9001:9001/tcp"
    env_file:
      - ./valheim-server/valheim.env
    restart: always
    stop_grace_period: 2m
"""
    with open(path / "compose.yaml","w") as f:
        f.write(content)
    
    logger.info("Starting Valheim server")
    result = run_command(["docker","compose","up","-d"],logger,cwd=path)
    if result.returncode != 0:
        logger.warning("Docker compose failed to start Valheim")
    else:
        logger.info("Opening port 9001, 2456-2458 in ufw")
        run_ufw(9001,logger)
        run_ufw(2456,logger,"udp")
        run_ufw(2457,logger,"udp")
        run_ufw(2458,logger,"udp")
        logger.info("Running Valheim on 2456-2458")

def install_palworld(args,logger):
    # creates docker compose file and creates and runs palworld container on 8211
    logger.info("Installing Palworld")
    logger.info("Creating Palworld directory")
    path = pathlib.Path("/srv") / args.mode / "palworld"
    user = get_user()
    create_dir(path,user,args.dir_group)
    create_dir(path / "palworld",user,args.dir_group)
    content = f"""services:
   palworld:
      image: thijsvanloef/palworld-server-docker:latest
      restart: unless-stopped
      container_name: palworld-server
      stop_grace_period: 30s # Set to however long you are willing to wait for the container to gracefully stop
      ports:
        - "8211:8211/udp"
        - "27015:27015/udp"
      environment:
         PUID: 1000
         PGID: 1000
         PORT: 8211
         PLAYERS: 16
         SERVER_PASSWORD: CHANGE-ME
         MULTITHREADING: true
         RCON_ENABLED: true
         RCON_PORT: 25575
         TZ: "UTC"
         ADMIN_PASSWORD: CHANGE-ME
         COMMUNITY: false
         SERVER_NAME: {args.world_name}
         SERVER_DESCRIPTION: {args.world_name}
      volumes:
         - ./palworld:/palworld/
"""
    with open(path / "compose.yaml","w") as f:
        f.write(content)
    
    logger.info("Starting Palworld server")
    result = run_command(["docker","compose","up","-d"],logger,cwd=path)
    if result.returncode != 0:
        logger.warning("Docker compose failed to start Palworld")
    else:
        logger.info("Opening port 8211, 27015 in ufw")
        run_ufw(8211,logger,"udp")
        run_ufw(27015,logger,"udp")
        logger.info("Running Palworld on 8211")    

# =================================
# Main mode functions
# =================================

def do_game_mode(args, logger):
    # does game mode
    if "all" in args.game or "minecraft" in args.game:
        install_minecraft(args,logger)
    if "all" in args.game or "valheim" in args.game:
        install_valheim(args,logger)
    if "all" in args.game or "palworld" in args.game:
        install_palworld(args,logger)
    if "all" in args.game or "windrose" in args.game:
        install_windrose(args,logger)        

def do_compute_mode(args, logger):
    # does compute mode
    user = get_user()
    install_python_git_buildessential(logger)
    configure_flask_page(args,logger)
    configure_wiki(args,logger)

def do_boundary_mode(args, logger):
    # does boundary mode
    install_caddy(args,logger)
    if args.vpn:
        install_vpn(logger)

def main():
    # then do the modes. Individual modes should prompt for any missing information
    # verify ran as root, get arguments, get user that ran the script, setup logging, then do a mode
    args = parse_args()
    logfile = make_logfile_name(args)
    logger = setup_logger(args.verbose, logfile)
    verify_root(logger)
    get_user()
    configure_common(args, logger)
    mode = args.mode
    if mode == "game":
        do_game_mode(args, logger)
    elif mode == "compute":
        do_compute_mode(args, logger)
    elif mode == "boundary":
        do_boundary_mode(args, logger)
    else:
        sys.exit(1)
    
if __name__ == "__main__":
    main()