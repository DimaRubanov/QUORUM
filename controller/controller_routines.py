import datetime
import json
import random
import time

from tornado.httpclient import HTTPRequest

def log(config, line):
    print(line)
    try:
        with open(config["log_file"], "a") as fp:
            fp.write(str(datetime.datetime.now()) + "\n")
            fp.write("    " + line + "\n\n")
    except KeyError:
        pass

def get_auth_headers(http_client, config):
    url = config["identity_endpoint"] + "/v3/auth/tokens"
    body = json.dumps({"auth": config["auth"]})
    headers = {"Content-Type": "application/json"}
    request = HTTPRequest(url, method = "POST", headers = headers, body = body)
    response = http_client.fetch(request)
    headers["X-Auth-Token"] = response.headers["X-Subject-Token"]
    return headers

def create_server(http_client, config, auth_headers, image=None):
    url = config["compute_endpoint"] + "/servers"
    params = config["server"].copy()
    server_name = params["name"] + "-" +  hex(random.randrange(0, 0xffffffff))
    params["name"] += server_name
    if image:
        params["imageRef"] = image["id"]
    body = json.dumps({"server": params})
    request = HTTPRequest(url, method = "POST", headers = auth_headers, body = body)
    response = http_client.fetch(request)
    server_id = json.loads(response.body.decode())["server"]["id"]
    return {"id": server_id, "name": server_name}

def get_ip(http_client, config, auth_headers, server):
    url = config["compute_endpoint"] + "/servers/" + server["id"]
    request = HTTPRequest(url, method = "GET", headers = auth_headers)
    while True:
        response = http_client.fetch(request)
        serv = json.loads(response.body.decode())["server"]
        if config["network_name"] in serv["addresses"]:
            addrs = [addr for addr in serv["addresses"][config["network_name"]] if addr["version"] == config["ip_version"]]
            if len(addrs) > 0:
                server["ip"] = addrs[0]["addr"] 
                return
        log(config, "Waiting for IP: " + str(server))
        time.sleep(5)

def wait_until_start(http_client, config, server):
    url = "http://" + server["ip"] + ":" + str(config["test_port"]) + config["test_uri"]
    while True:
        try:
            http_client.fetch(url)
        except:
            log(config, "Waiting for start: " + str(server))
            time.sleep(5)
        else:
            return
        
def proxy_set_param(http_client, config, name, value):
    url = config["proxy_endpoint"]
    body = json.dumps({name: value})
    request = HTTPRequest(url, method = "POST", body = body)
    http_client.fetch(request)
        
def proxy_set_servers(http_client, config, servers):
    p_servers = [server["ip"] + ":" + str(config["server_port"]) for server in servers]
    proxy_set_param(http_client, config, "servers", p_servers)

def proxy_get_params(http_client, config):
    url = config["proxy_endpoint"]
    response = http_client.fetch(url)
    return json.loads(response.body.decode())

def start_cluster(http_client, config):
    log(config, "START CLUSTER")
    auth_headers = get_auth_headers(http_client, config)
    log(config, "Authenticated")
    servers = []
    for _ in range(config["number_of_servers"]):
        server = create_server(http_client, config, auth_headers)
        servers.append(server)
        log(config, "Created " + str(server))
    for server in servers:
        get_ip(http_client, config, auth_headers, server)
        log(config, "Got IP "+ str(server))
    for server in servers:
        wait_until_start(http_client, config, server)
        log(config, "Started " + str(server))
    proxy_set_param(http_client, config, "quorum", config["quorum"])
    proxy_set_servers(http_client, config, servers)
    proxy_set_param(http_client, config, "running", True)
    log(config, "Proxy configured")
    log(config, "CLUSTER STARTED")
    return servers

def server_action(http_client, config, auth_headers, server, name, value):
    url = config["compute_endpoint"] + "/servers/" + server["id"] + "/action"
    body = json.dumps({name: value})
    request = HTTPRequest(url, method = "POST", headers = auth_headers, body = body)
    http_client.fetch(request)
    
def get_image_id(http_client, config, auth_headers, image):
    url = config["image_endpoint"] + "/v2/images?name=" + image["name"]
    request = HTTPRequest(url, method="GET", headers = auth_headers)
    response = http_client.fetch(request)
    images = json.loads(response.body.decode())["images"]
    image["id"] = images[0]["id"]
    
def wait_for_image(http_client, config, auth_headers, image):
    url = config["image_endpoint"] + "/v2/images/" + image["id"]
    request = HTTPRequest(url, method="GET", headers = auth_headers)
    while True:
        response = http_client.fetch(request)
        status = json.loads(response.body.decode())["status"]
        if status == "active":
            return
        log(config, "Waiting for image")
        time.sleep(5)

def check_cluster(http_client, config, servers):
    log(config, "CLUSTER CHECK")
    params = proxy_get_params(http_client, config)
    p_ips = [s.split(":")[0] for s in params["servers"]]
    ips = [s["ip"] for s in servers]
    if sorted(p_ips) == sorted(ips):
        log(config, "CLUSTER OK")
        return
    proxy_set_param(http_client, config, "running", False)
    log(config, "Proxy paused")
    auth_headers = get_auth_headers(http_client, config)
    donors = [s for s in servers if s["ip"] in p_ips]
    failed = [s for s in servers if s not in donors]
    log(config, "Donors: " + str(donors))
    log(config, "Failed: " + str(failed))
    for server in failed:
        server_action(http_client, config, auth_headers, server, "pause", None)
        log(config, "Paused" + str(server))
    if len(donors) == 0:
        log(config, "CLUSTER FAILED")
        return
    donor = donors[0]
    image = {}
    image["name"] = donor["name"] + "-" + hex(random.randrange(0, 0xffffffff))
    server_action(http_client, config, auth_headers, donor, 
                  "createImage", {"name": image["name"]})
    log(config, "Image created " + str(image))
    get_image_id(http_client, config, auth_headers, image)
    log(config, "Image id got " + str(image))
    wait_for_image(http_client, config, auth_headers, image)
    log(config, "Image ready")
    new_servers = []
    for _ in range(config["number_of_servers"] - len(donors)):
        server = create_server(http_client, config, auth_headers, image)
        new_servers.append(server)
        log(config, "Started " + str(server))
    for server in new_servers:
        get_ip(http_client, config, auth_headers, server)
        log(config, "Got ip "+ str(server))
    for server in new_servers:
        wait_until_start(http_client, config, server)
        log(config, "Started "+ str(server))
    servers.clear()
    servers += donors
    servers += new_servers
    proxy_set_servers(http_client, config, servers)
    proxy_set_param(http_client, config, "running", True)
    log(config, "Proxy paused")
    log(config, "CLUSTER RECOVERED")