```
   +------------+          +-----------------------------+           +------------+
   |  SOCKS5    |  SOCKS5  |                             |  WebSocket |  Proxy     |
   |  Client 1  |<-------->|    Service (Public Server)  |<---------->|  Server 1  |
   +------------+          |   (SOCKS5 on WebSocket)      |           +------------+
                           |                             | 
   +------------+          |                             |           +------------+
   |  SOCKS5    |  SOCKS5  |                             |  WebSocket |  Proxy     |
   |  Client 2  |<-------->|    Service (Public Server)  |<---------->|  Server 2  |
   +------------+          |   (SOCKS5 on WebSocket)      |           +------------+
                           |                             |
   +------------+          |                             |           +------------+
   |  SOCKS5    |  SOCKS5  |                             |  WebSocket |  Proxy     |
   |  Client N  |<-------->|    Service (Public Server)  |<---------->|  Server N  |
   +------------+          +-----------------------------+           +------------+
                         ((SOCKS5 requests through WebSocket))
```
