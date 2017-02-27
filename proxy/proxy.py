import datetime
import json
import random

import tornado.httpclient
import tornado.httpserver
import tornado.ioloop
import tornado.queues
import tornado.web

PORT = 8000
CONF_PORT = 7777
LOG_FILE = "proxy.log"
CONF_FILE = "proxy.conf"

RUNNING = False
SERVERS = []
QUORUM = None
CLIENT_ERRORS = range(400, 500)
SERVER_ERRORS = range(500, 600)

def log(line):
    print(line)
    try:
        with open(LOG_FILE, "a") as fp:
            fp.write(str(datetime.datetime.now()) + "\n")
            fp.write("    " + line + "\n\n")
    except KeyError:
        pass

def get_params():
    return {
        'running': RUNNING,
        'quorum': QUORUM,
        'servers': SERVERS,
    }

def set_params(params):
    log("set_params: " + json.dumps(params))
    if 'running' in params:
        global RUNNING
        RUNNING = params['running']
    if 'quorum' in params:
        global QUORUM
        QUORUM = params['quorum']
    if 'servers' in params:
        global SERVERS
        SERVERS = params['servers']
        
def update_config():
    with open(CONF_FILE, "w") as fp:
            json.dump(get_params(), fp)

def declare_failure(server):
    SERVERS.remove(server)
    update_config()
    log("server failed: " + server)

def declare_global_failure():
    global SERVERS
    SERVERS = []
    global RUNNING
    RUNNING = False
    update_config()
    log("global failure")
    
class RESTRequestHandler(tornado.web.RequestHandler):
    
    async def get(self):
        self.set_status(200)
        self.finish(json.dumps(get_params()))
    
    async def post(self):
        self.set_status(200)    
        params = json.loads(self.request.body.decode())
        set_params(params)
        self.finish(json.dumps(get_params()))
        update_config()

try:
    with open(CONF_FILE, "r") as fp:
        set_params(json.load(fp))
except FileNotFoundError:
    pass
rest_app = tornado.web.Application([
        ("/params", RESTRequestHandler),
    ])
rest_server = tornado.httpserver.HTTPServer(rest_app)
rest_server.listen(CONF_PORT)    

class ProxyRequestHandler(tornado.web.RequestHandler):
    
    async def prepare(self):
        
        global RUNNING
        if not RUNNING:
            self.send_error(503)
            return
        uri = self.request.uri
        method = self.request.method
        if method in ["GET"]:
            body = None
        else:
            body = self.request.body
        headers = self.request.headers
        headers.add("X-Quorum-Seed", hex(random.randrange(0, 0xffffffff)))
        queue = tornado.queues.Queue()
        servers_n = len(SERVERS)
        for server_id, server in enumerate(SERVERS):
            request = tornado.httpclient.HTTPRequest(method=method,
                url="http://" + server + uri,
                headers=headers, body=body)
            request.headers["X-Quorum-ID"] = str(server_id)
            tornado.httpclient.AsyncHTTPClient().fetch(request,
                lambda response, server = server: queue.put((server, response)))
            
        servers_by_hash_codes = {}
        final_hash_code = None
        for _ in range(servers_n):
            server, response = await queue.get()
            x_hash = response.headers.get("X-Quorum-Hash", None)
            code = response.code
            if code == 304:
                code = 200
            hash_code = (x_hash, code)
            
            if response.error:
                if response.code in SERVER_ERRORS:
                    declare_failure(server)
                    continue
                
            if final_hash_code:
                if final_hash_code != hash_code:
                    declare_failure(server)
                continue
            
            servers_by_hash_codes.setdefault(hash_code, []).append(server)
            
            if len(servers_by_hash_codes[hash_code]) == QUORUM:
                final_hash_code = hash_code
                self.set_status(response.code)
                for name, value in response.headers.items():
                    self.set_header(name, value)
                if response.code != 304:
                    self.write(response.body)
                self.finish()
                
                for wrong_hash_code, failed_servers in servers_by_hash_codes.items():
                    if (wrong_hash_code == final_hash_code):
                        continue
                    for failed_server in failed_servers:
                        declare_failure(failed_server)
                        
        if final_hash_code == None:
            declare_global_failure()
            self.send_error(503)


proxy_app = tornado.web.Application([
        (r".*", ProxyRequestHandler),
    ])
proxy_server = tornado.httpserver.HTTPServer(proxy_app)
proxy_server.listen(PORT)

tornado.ioloop.IOLoop.current().start()
