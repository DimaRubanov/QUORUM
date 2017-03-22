# QUORUM

QUORUM is a solution that increases availability and reliability of HTTP servers in the OpenStack context. Its principles are described in my PFE report.

The user should properly configure an HTTP server and save an image of it to OpenStack. This image will be used by QUORUM to start the cluster. This repository contains a dump HTTP server for testing.

The proxy must be launched before the controller. It listens on two ports: one for actual user's requests and one for configuration commands from the controller. Port numbers can be changed in the file proxy.py.

The controller must be configured with the file controller.conf. It contains OpenStack API endpoints, authentification credentials, server templates, proxy's address and port etc.

You can find a quick demonstration of QUORUM here: https://www.youtube.com/watch?v=nOqXCHBRJEs

For any questions please contact dmytro.rubanov@etu.unice.fr.
