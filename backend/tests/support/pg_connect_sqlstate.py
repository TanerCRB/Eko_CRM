"""Connect to PostgreSQL over the wire and report the SQLSTATE of a refusal (K-03, ADR-0003-C11).

libpq, and so psycopg, gives no SQLSTATE for a refused connection; the server's ErrorResponse
carries it. Standard library only: the runtime tests send this file, prefixed with a line
`cases = [(host, role, password, database), ...]`, to `python -` in the backend container, so no
password reaches a command line. It writes one JSON list: "ok" or the SQLSTATE for each case.
"""

import base64
import hashlib
import hmac
import json
import os
import socket
import struct
import sys

PROTOCOL_3 = 196608


def _message(sock: socket.socket) -> tuple[bytes, bytes]:
    header = _read(sock, 5)
    length = struct.unpack("!I", header[1:])[0]
    return header[:1], _read(sock, length - 4)


def _read(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("server closed the connection")
        data += chunk
    return data


def _send(sock: socket.socket, kind: bytes, payload: bytes) -> None:
    sock.sendall(kind + struct.pack("!I", len(payload) + 4) + payload)


def _sqlstate(payload: bytes) -> str:
    for field in payload.split(b"\0"):
        if field[:1] == b"C":
            return field[1:].decode()
    return "no-sqlstate"


def attempt(host: str, user: str, password: str, database: str) -> str:
    with socket.create_connection((host, 5432), timeout=10) as sock:
        params = b"user\0" + user.encode() + b"\0database\0" + database.encode() + b"\0\0"
        body = struct.pack("!I", PROTOCOL_3) + params
        sock.sendall(struct.pack("!I", len(body) + 4) + body)
        nonce = base64.b64encode(os.urandom(18)).decode()
        first_bare = f"n=,r={nonce}"
        auth_message = ""
        key = b""
        while True:
            kind, payload = _message(sock)
            if kind == b"E":
                return _sqlstate(payload)
            if kind == b"Z":
                return "ok"
            if kind != b"R":
                continue
            code = struct.unpack("!I", payload[:4])[0]
            if code == 10:  # AuthenticationSASL
                first = ("n,," + first_bare).encode()
                data = b"SCRAM-SHA-256\0" + struct.pack("!I", len(first)) + first
                _send(sock, b"p", data)
            elif code == 11:  # AuthenticationSASLContinue
                server_first = payload[4:].decode()
                fields = dict(item.split("=", 1) for item in server_first.split(","))
                salt = base64.b64decode(fields["s"])
                salted = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(fields["i"]))
                key = hmac.new(salted, b"Client Key", "sha256").digest()
                stored = hashlib.sha256(key).digest()
                without_proof = f"c=biws,r={fields['r']}"
                auth_message = f"{first_bare},{server_first},{without_proof}"
                signature = hmac.new(stored, auth_message.encode(), "sha256").digest()
                proof = bytes(a ^ b for a, b in zip(key, signature, strict=True))
                final = f"{without_proof},p={base64.b64encode(proof).decode()}"
                _send(sock, b"p", final.encode())


if __name__ == "__main__":
    cases: list[tuple[str, str, str, str]] = globals().get("cases", [])
    sys.stdout.write(json.dumps([attempt(*case) for case in cases]))
