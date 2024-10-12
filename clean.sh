#!/bin/bash

rm bot_data.db 
docker rm $(docker ps -a -q) -f
rm -rf /etc/openvpn*