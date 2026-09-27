import json
import os
import socket
import threading
import time

import pytest

from damx_daemon import VERSION, paths
from damx_daemon.server import DaemonServer


class NoFeatures:
    available_features = set()


@pytest.fixture
def server(fake_system):
    server = DaemonServer(NoFeatures())
    threading.Thread(target=server.start, daemon=True).start()
    for _ in range(100):
        if os.path.exists(paths.SOCKET_PATH):
            break
        time.sleep(0.01)
    yield server
    server.stop()


def connect():
    client = socket.socket(socket.AF_UNIX)
    client.connect(paths.SOCKET_PATH)
    client.settimeout(2)
    return client


def receive(client):
    return json.loads(client.recv(65536))


def test_ping(server):
    with connect() as client:
        client.sendall(b'{"command": "ping"}')
        assert receive(client) == {"success": True}


def test_request_split_across_reads(server):
    with connect() as client:
        client.sendall(b'{"command": "get_ver')
        time.sleep(0.03)
        client.sendall(b'sion"}')
        assert receive(client) == {"success": True, "data": {"version": VERSION}}


def test_two_requests_in_one_read(server):
    with connect() as client:
        client.sendall(b'{"command": "ping"}{"command": "ping"}')
        time.sleep(0.2)
        assert client.recv(65536) == b'{"success": true}{"success": true}'


@pytest.mark.parametrize("request_bytes, error", [
    (b"{not json", "Invalid JSON format"),
    (b"[1, 2]", "Request must be a JSON object"),
    (b'{"command": "nope"}', "Unknown command: nope"),
])
def test_bad_requests(server, request_bytes, error):
    with connect() as client:
        client.sendall(request_bytes)
        assert receive(client) == {"success": False, "error": error}


def test_connections_beyond_the_limit_are_refused(server):
    clients = [connect() for _ in range(DaemonServer.MAX_CLIENTS)]
    time.sleep(1.5)  # the accept loop polls once a second
    extra = connect()
    extra.sendall(b'{"command": "ping"}')
    with pytest.raises((ConnectionResetError, json.JSONDecodeError)):
        receive(extra)
    for client in clients:
        client.close()
