import json

import tornado.httpclient

from controller_routines import start_cluster, check_cluster

CONF_FILE = "controller.conf"
SERVERS_FILE = "server_list.conf"

with open(CONF_FILE, "r") as fp:
    config = json.load(fp)

http_client = tornado.httpclient.HTTPClient()

try:
    with open(SERVERS_FILE, "r") as fp:
        servers = json.load(fp)
    check_cluster(http_client, config, servers)
    with open(SERVERS_FILE, "w") as fp:
        json.dump(servers, fp)
except FileNotFoundError:
    servers = start_cluster(http_client, config)
    with open(SERVERS_FILE, "w") as fp:
        json.dump(servers, fp)