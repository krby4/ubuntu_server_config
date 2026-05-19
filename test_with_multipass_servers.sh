#!/usr/bin/env bash
# Create the three VMs with enough disk to do everything, in total 35GB disk is taken
multipass launch 24.04 --name boundaryTest
multipass launch 24.04 --name computeTest --disk 10G
multipass launch 24.04 --name gameTest --disk 20G
# Transfer the files needed for monitoring and the script
multipass transfer /home/keith/code/344projects/final/ubuntu_server_config.py boundaryTest:
multipass transfer /home/keith/code/344projects/final/config/ -r config boundaryTest:
multipass transfer /home/keith/code/344projects/final/ubuntu_server_config.py computeTest:
multipass transfer /home/keith/code/344projects/final/config/ -r config computeTest:
multipass transfer /home/keith/code/344projects/final/ubuntu_server_config.py gameTest:
multipass transfer /home/keith/code/344projects/final/config/ -r config gameTest:
# Execute the commands
multipass exec boundaryTest -- sudo python3 ubuntu_server_config.py boundary --vpn --domain-name test.domain -l "out.log"
multipass exec computeTest -- sudo python3 ubuntu_server_config.py compute --domain-name test.domain --monitoring --wiki-name mywiki
multipass exec gameTest -- sudo python3 ubuntu_server_config.py game -g "all"

# Using the below command you can delete and purge multipass, though deleting 3 at once sometimes hangs
# multipass delete gameTest && multipass delete boundaryTest && multipass delete computeTest && multipass purge
# start an interactive shell on the vm
# multipass shell <host>
# Test the homepage
# start a shell in the vm then run: hostname -I then curl http://hostip:5000
# Test the wiki
# start a shell in the vm then run: hostname -I then curl http://hostip:3000
# check docker containers that are running
# docker stats
# Check the systemd stuff
# sudo systemctl status