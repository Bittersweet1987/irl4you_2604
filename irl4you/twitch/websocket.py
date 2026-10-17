"""IRL4YOU BOX Twitch: einfacher WebSocket-Client."""

import base64
import hashlib
import os
import re
import socket
import time


class WebSocketLite:
    GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    MAX = 1 << 20

    def __init__(self, sock, clock=time.monotonic):
        self.sock, self.clock = sock, clock
        self.buf = bytearray()
        self.parts, self.first = bytearray(), None
        self.last_rx = clock()

    @classmethod
    def handshake(cls, sock, host, path, clock=time.monotonic, timeout=10.0):
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall(b"GET " + path.encode("ascii") + b" HTTP/1.1\r\nHost: " + host.encode("ascii") + b"\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: "
                     + key.encode("ascii") + b"\r\nSec-WebSocket-Version: 13\r\nUser-Agent: irl4you-box\r\n\r\n")
        buf, deadline = b"", clock() + timeout
        while b"\r\n\r\n" not in buf:
            left = deadline - clock()
            if left <= 0 or len(buf) > 16384:
                raise OSError("ws-handshake-timeout")
            sock.settimeout(left)
            chunk = sock.recv(4096)
            if not chunk:
                raise EOFError("ws-eof")
            buf += chunk
        head, _, rest = buf.partition(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        if not re.match(r"HTTP/1\.[01] 101\b", lines[0]):
            raise OSError("ws-no-upgrade")
        hdr = {k.strip().lower(): v.strip() for k, _, v in (l.partition(":") for l in lines[1:])}
        want = base64.b64encode(hashlib.sha1(key.encode("ascii") + cls.GUID).digest()).decode()
        if hdr.get("sec-websocket-accept") != want:
            raise OSError("ws-bad-accept")
        ws = cls(sock, clock)
        ws.buf += rest
        return ws

    @staticmethod
    def frame(opcode, payload=b""):
        mask, n = os.urandom(4), len(payload)
        head = bytes([0x80 | opcode])
        head += bytes([0x80 | n]) if n < 126 else (bytes([0x80 | 126]) + n.to_bytes(2, "big") if n < 65536 else bytes([0x80 | 127]) + n.to_bytes(8, "big"))
        return head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))

    def close(self):
        try:
            self.sock.sendall(self.frame(8, b"\x03\xe8"))
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    def _need(self, n, deadline):
        while len(self.buf) < n:
            left = deadline - self.clock()
            if left <= 0:
                return False
            self.sock.settimeout(left)
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                return False
            if not chunk:
                raise EOFError("ws-eof")
            self.last_rx = self.clock()
            self.buf += chunk
        return True

    def recv_message(self, timeout):
        deadline = self.clock() + timeout
        while True:
            if self.clock() > deadline:
                return None
            if not self._need(2, deadline):
                return None
            b0, b1 = self.buf[0], self.buf[1]
            fin, op = b0 & 0x80, b0 & 0x0f
            if (b0 & 0x70) or (b1 & 0x80):
                raise OSError("ws-protocol")
            ln, off = b1 & 0x7f, 2
            if ln == 126:
                if not self._need(4, deadline):
                    return None
                ln, off = int.from_bytes(self.buf[2:4], "big"), 4
            elif ln == 127:
                if not self._need(10, deadline):
                    return None
                ln, off = int.from_bytes(self.buf[2:10], "big"), 10
            if ln > self.MAX or (op >= 8 and (not fin or ln > 125)):
                raise OSError("ws-protocol")
            if not self._need(off + ln, deadline):
                return None
            payload = bytes(self.buf[off:off + ln])
            del self.buf[:off + ln]
            if op == 9:
                self.sock.sendall(self.frame(10, payload))
                continue
            if op == 10:
                continue
            if op == 8:
                raise EOFError("ws-closed")
            if op in (1, 2):
                if self.first is not None:
                    raise OSError("ws-protocol")
                self.first = op
            elif op == 0:
                if self.first is None:
                    raise OSError("ws-protocol")
            else:
                raise OSError("ws-protocol")
            self.parts += payload
            if len(self.parts) > self.MAX:
                raise OSError("ws-too-big")
            if fin:
                data, kind = bytes(self.parts), self.first
                self.parts, self.first = bytearray(), None
                if kind != 1:
                    raise OSError("ws-not-text")
                return data.decode("utf-8")
