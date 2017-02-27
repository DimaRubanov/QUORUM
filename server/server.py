import datetime
import random

import tornado.gen
import tornado.httpserver
import tornado.ioloop
import tornado.web

LOG_FILE = "server.log"
LOGGING = True
PORT = 8000

class MainHandler(tornado.web.RequestHandler):
    async def prepare(self):
        uri = self.request.uri
        method = self.request.method
        headers = self.request.headers
        body = self.request.body
        server_id = headers.get("X-Quorum-ID", default="0")
        try:
            delay = float(self.get_argument("delay" + server_id))
        except tornado.web.MissingArgumentError:
            delay = random.random() * 3
        try:
            seed = int(headers["X-Quorum-Seed"], 16)
        except KeyError:
            seed = random.randrange(0, 0xffffffff)
        random.seed(seed)
        X_hash = self.get_argument("hash" + server_id, default = uri + hex(seed))
        try:
            code = int(self.get_argument("code" + server_id))
        except tornado.web.MissingArgumentError:
            code = 200
        resp = self.get_argument("response" + server_id, default = \
            "server: " + server_id + " method: " + method +  " uri: " + uri + \
            " X-Quorum-Hash: " + X_hash + " delay: " + str(delay))
        if LOGGING:
            with open(LOG_FILE, "a") as f:
                f.write(str(datetime.datetime.now()) + "\nseed: " + hex(seed) + "\n")
                f.write("REQUEST\n")
                f.write("    " + method + " " + uri + "\n")
                f.write("    headers:\n")
                for name, value in headers.items():
                    f.write("        " + name + " : " + value + "\n")
                f.write("    body:\n\n" + body.decode() + "\n\n")
                f.write("    delay: " + str(delay) + "\n\n\n\n\n")
        await tornado.gen.sleep(delay)
        self.set_status(code)
        if code in range(200, 300):
            self.set_header("X-Quorum-Hash", X_hash)
            self.write(resp)
        self.finish()
        if LOGGING:
            with open(LOG_FILE, "a") as f:
                f.write(str(datetime.datetime.now()) + "\nseed: " + hex(seed) + "\n")
                f.write("RESPONSE\n")
                f.write("    code: " + str(code) + "\n")
                if (code in range(200, 300)):
                    f.write("    X-Quorum-Hash: " + X_hash + "\n")
                    f.write("    body:\n\n" + resp + "\n\n\n\n\n")
                
app = tornado.web.Application([
        (r".*", MainHandler),
    ])
server = tornado.httpserver.HTTPServer(app)
server.listen(PORT)
tornado.ioloop.IOLoop.current().start()
