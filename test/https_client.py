#!/usr/bin/python3
import socket, ssl, os

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE
sslSocket = context.wrap_socket(s, server_hostname='127.0.0.1')
sslSocket.connect(("127.0.0.1", 4443))

request_header = 'GET / HTTP/1.0\r\nHost: sometest.domain\r\n\r\n'
sslSocket.send(request_header.encode())

response = ''
while True:
    recv = sslSocket.recv(1024)
    if not recv:
        break
    response += str(recv) 

print(response)
sslSocket.close()    
print(os.system('grep VmRSS /proc/' + str(os.getpid()) + '/status'))