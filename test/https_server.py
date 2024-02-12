#!/usr/bin/python3
"""
openssl req -newkey rsa:2048 -nodes -keyout server.key -out server.csr
openssl x509 -signkey server.key -in server.csr -req -days 365 -out server.crt
"""
import http.server
import ssl

server_address = ('127.0.0.1', 4443)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain('server.crt', './server.key')
httpd = http.server.HTTPServer(server_address, http.server.SimpleHTTPRequestHandler)
httpd.socket = context.wrap_socket(httpd.socket,server_hostname='sometest.domain')
httpd.serve_forever()