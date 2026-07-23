"""App-Shell: Portwahl und Serverstart."""
import socket

from src.app import find_free_port


def test_find_free_port_ist_bindbar():
    port = find_free_port()
    assert 1024 <= port <= 65535
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", port))
