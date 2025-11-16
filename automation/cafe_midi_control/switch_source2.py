"""
This script will use the Kramer Protocol 3000 interface to switch the
SWT3-41-H from it's current source to source 2.
"""

from proto3k import SocketConnection, Route


with SocketConnection(host="192.168.1.208", port=5000) as connection:
   connection.send_message(Route(2))


