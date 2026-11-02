#!/usr/local/bin/python3
"""The destination double's recorder (ADR-0004 addendum 2026-10-30, *The destination double*).

sshd forces every session of the double through this program. For each SFTP request the client
sends, it appends one JSON line to the access record (the credential, the client address, the
request type, the name, the open flags and whether the name existed at that moment), then passes
the bytes on to /usr/lib/openssh/sftp-server. The record is written before the server sees the
request, so a refused request is recorded like an accepted one.

/etc/eko-double/mode selects the server's flags for the backup account:
  on             the destination's flags: allow list and umask 0377
  off            refusal switched off: no allow list, an ordinary umask
  lose-complete  as `on`, but a closed `*.complete` object is lost (removed) before the client
                 hears that the close succeeded
The administrative credential (root) always runs without the allow list.
"""

import json
import os
import struct
import subprocess
import sys
import threading
from datetime import UTC, datetime
from typing import IO

RECORD = "/var/log/eko-double/access.jsonl"
MODE_FILE = "/etc/eko-double/mode"
SERVER = "/usr/lib/openssh/sftp-server"
ALLOW_LIST = "open,write,close,stat,lstat,fstat,realpath"
DESTINATION_FLAGS = ["-l", "VERBOSE", "-u", "0377", "-p", ALLOW_LIST]
REFUSAL_OFF_FLAGS = ["-l", "VERBOSE", "-u", "0022"]

TYPES = {
    1: "init", 3: "open", 4: "close", 5: "read", 6: "write", 7: "lstat", 8: "fstat",
    9: "setstat", 10: "fsetstat", 11: "opendir", 12: "readdir", 13: "remove", 14: "mkdir",
    15: "rmdir", 16: "realpath", 17: "stat", 18: "rename", 19: "readlink", 20: "symlink",
    200: "extended",
}  # fmt: skip
PATH_REQUESTS = {7, 9, 11, 13, 14, 15, 16, 17, 19}
HANDLE_REQUESTS = {4, 5, 6, 8, 10, 12}
TWO_PATH_REQUESTS = {18, 20}
# OpenSSH's extensions that name two paths, by the part of their name before the vendor suffix.
TWO_PATH_EXTENSIONS = {"posix-rename", "hardlink"}
OPEN_FLAGS = {
    0x01: "READ", 0x02: "WRITE", 0x04: "APPEND", 0x08: "CREAT", 0x10: "TRUNC", 0x20: "EXCL",
}  # fmt: skip
FXP_OPEN, FXP_CLOSE, FXP_EXTENDED = 3, 4, 200
FXP_STATUS, FXP_HANDLE = 101, 102


class Packets:
    def __init__(self, stream: IO[bytes]) -> None:
        self.stream = stream

    def next(self) -> bytes | None:
        header = self._exactly(4)
        if header is None:
            return None
        body = self._exactly(struct.unpack("!I", header)[0])
        return None if body is None else header + body

    def _exactly(self, size: int) -> bytes | None:
        data = b""
        while len(data) < size:
            chunk = self.stream.read(size - len(data))
            if not chunk:
                return None
            data += chunk
        return data


def string_at(body: bytes, offset: int) -> tuple[bytes, int]:
    length = struct.unpack("!I", body[offset : offset + 4])[0]
    start = offset + 4
    return body[start : start + length], start + length


class Recorder:
    def __init__(self, credential: str, client: str, mode: str) -> None:
        self.credential = credential
        self.client = client
        self.mode = mode
        self.lock = threading.Lock()
        self.pending_opens: dict[int, str] = {}
        self.pending_closes: dict[int, str] = {}
        self.handles: dict[bytes, str] = {}

    def resolve(self, name: str) -> str:
        return name if name.startswith("/") else os.path.join(os.getcwd(), name)

    def existed(self, name: str) -> bool:
        return os.path.lexists(self.resolve(name))

    def write(self, entry: dict[str, object]) -> None:
        now = datetime.now(UTC).isoformat()
        entry = {"at": now, "credential": self.credential, "client": self.client, **entry}
        line = (json.dumps(entry, sort_keys=True) + "\n").encode()
        with self.lock:
            descriptor = os.open(RECORD, os.O_WRONLY | os.O_APPEND)
            try:
                os.write(descriptor, line)
            finally:
                os.close(descriptor)

    def client_packet(self, packet: bytes) -> None:
        body = packet[4:]
        kind = body[0]
        entry: dict[str, object] = {"request": TYPES.get(kind, f"type-{kind}")}
        if kind != 1:
            request_id = struct.unpack("!I", body[1:5])[0]
            offset = 5
            if kind == FXP_OPEN:
                raw, offset = string_at(body, offset)
                name = raw.decode(errors="replace")
                flags = struct.unpack("!I", body[offset : offset + 4])[0]
                entry |= {
                    "name": name,
                    "flags": [label for bit, label in OPEN_FLAGS.items() if flags & bit],
                    "existed": self.existed(name),
                }
                self.pending_opens[request_id] = name
            elif kind in PATH_REQUESTS:
                raw, _ = string_at(body, offset)
                name = raw.decode(errors="replace")
                entry |= {"name": name, "existed": self.existed(name)}
            elif kind in HANDLE_REQUESTS:
                handle, _ = string_at(body, offset)
                name = self.handles.get(handle, "")
                entry |= {"name": name, "existed": bool(name) and self.existed(name)}
                if kind == FXP_CLOSE:
                    self.pending_closes[request_id] = name
            elif kind in TWO_PATH_REQUESTS:
                self._two_paths(entry, body, offset)
            elif kind == FXP_EXTENDED:
                raw, offset = string_at(body, offset)
                extension = raw.decode(errors="replace")
                entry["extension"] = extension
                if extension.split("@")[0] in TWO_PATH_EXTENSIONS:
                    self._two_paths(entry, body, offset)
        self.write(entry)

    def _two_paths(self, entry: dict[str, object], body: bytes, offset: int) -> None:
        first, offset = string_at(body, offset)
        second, _ = string_at(body, offset)
        name, target = first.decode(errors="replace"), second.decode(errors="replace")
        entry |= {
            "name": name,
            "existed": self.existed(name),
            "target": target,
            "target_existed": self.existed(target),
        }

    def server_packet(self, packet: bytes) -> None:
        body = packet[4:]
        kind = body[0]
        if kind not in (FXP_HANDLE, FXP_STATUS):
            return
        request_id = struct.unpack("!I", body[1:5])[0]
        if kind == FXP_HANDLE and request_id in self.pending_opens:
            handle, _ = string_at(body, 5)
            self.handles[handle] = self.pending_opens.pop(request_id)
            return
        self.pending_opens.pop(request_id, None)
        closed = self.pending_closes.pop(request_id, None)
        succeeded = struct.unpack("!I", body[5:9])[0] == 0
        if self.mode == "lose-complete" and succeeded and closed and closed.endswith(".complete"):
            os.unlink(self.resolve(closed))


def server_flags(credential: str, mode: str) -> list[str]:
    if credential == "root" or mode == "off":
        return REFUSAL_OFF_FLAGS
    return DESTINATION_FLAGS


def main() -> int:
    credential = os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown"
    try:
        with open(MODE_FILE, encoding="utf-8") as handle:
            mode = handle.read().strip() or "on"
    except OSError:
        mode = "on"
    # sshd sets SSH_CONNECTION: "<client address> <client port> <server address> <server port>".
    client = (os.environ.get("SSH_CONNECTION") or "unknown").split()[0]
    recorder = Recorder(credential, client, mode)
    server = subprocess.Popen(
        [SERVER, *server_flags(credential, mode)], stdin=subprocess.PIPE, stdout=subprocess.PIPE
    )
    assert server.stdin is not None and server.stdout is not None
    to_server, from_server = server.stdin, server.stdout

    def answers() -> None:
        packets = Packets(from_server)
        while (packet := packets.next()) is not None:
            recorder.server_packet(packet)
            sys.stdout.buffer.write(packet)
            sys.stdout.buffer.flush()

    replies = threading.Thread(target=answers, daemon=True)
    replies.start()
    requests = Packets(sys.stdin.buffer)
    while (packet := requests.next()) is not None:
        recorder.client_packet(packet)
        to_server.write(packet)
        to_server.flush()
    to_server.close()
    code = server.wait()
    replies.join(timeout=10)
    return code


if __name__ == "__main__":
    sys.exit(main())
