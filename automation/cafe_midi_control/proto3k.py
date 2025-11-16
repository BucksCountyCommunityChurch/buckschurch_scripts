"""
This file contains the Protocol 3000 logic for controlling
the Kramer device, based on the code you provided.
"""

import socket
import time
import re
import os
import sys
from typing import Optional, Any

# Port is now defined in 'listener_config.yaml' and passed to KramerSocketConnection.
# Removed: PROTO3K_PORT = 5000

class KramerMessage:
    command="BASECLASS"
    P3K_RESPONSE_RE = "[~]([0-9])+[@](.*) ((?:.*)[,]{0,1})\r\n"

    def get_command(self) -> str:
        raise NotImplementedError("get_command() not implemented")

    def handle_response(self, response: str):
        raise NotImplementedError("get_command() not implemented")

    def _parse_response(self, response: str) -> dict:
        match = re.search(KramerMessage.P3K_RESPONSE_RE, response)
        if not match:
            print(f"[Kramer] Warning: Could not parse response: {response!r}")
            return {}
        result = {
            'device': match.group(1),
            'command': match.group(2),
            'params': match.group(3)
        }
        return result

class KramerProtocol:
    """
    A wrapper class that provides Kramer Protocol 3000 command
    passing over an established connection.
    """
    def __init__(self, sock: socket.socket, host: str, port: int):
        self._sock = sock
        self._host = host
        self._port = port
        print(f"[{host}:{port}] Protocol 3000 manager initialized on connected socket.")
        # Send the initial handshake
        self.send_message(Handshake())

    def send_message(self, msg: KramerMessage):
        """
        Converts the string message to a bytearray and sends it over the socket.
        """
        try:
            command = msg.get_command()
            data_bytes = command.encode('utf-8')
            data_bytearray = bytearray(data_bytes)
            
            self._sock.sendall(data_bytearray)
            print(f"[{self._host}:{self._port}] {msg.command} sent(len={len(data_bytearray)}): {data_bytearray!r}")

            # Set a timeout for the response
            self._sock.settimeout(0.5)
            data = self._sock.recv(1024)
            print(f"[{self._host}:{self._port}] Response Received: (len={len(data)}): {data!r}")
            decoded_data = data.decode('utf-8')

            resp_msg = msg.handle_response(decoded_data)
            if resp_msg:
                print(f"[{self._host}:{self._port}] {resp_msg}")
        except socket.timeout:
            print(f"[{self._host}:{self._port}] Warning: No response received from Kramer.")
        except Exception as ex:
            print(f"[{self._host}:{self._port}] Error Sending Kramer command: {ex!r}")
        time.sleep(0.5) # As in your original code


class Handshake(KramerMessage):
    def __init__(self):
        self.command="Handshake"

    def get_command(self) -> str:
        return "#\r"
        
    def handle_response(self, response: str):
        resp = self._parse_response(response)
        if not resp or resp.get('params') != 'OK':
           raise RuntimeError(f"Unable to establish interface with Kramer device {resp.get('device')}")
        return f"Response from Kramer device {resp['device']}: Handshake OK"


class Route(KramerMessage):
    LAYER_VIDEO=1
    LAYER_USB=5
    def __init__(self, source: int, dest: int = 1, layer: int = LAYER_VIDEO):
        self.command="Route"
        self.layer = layer
        self.dest = dest
        self.source = int(source)
    
    def get_command(self) -> str:
        return f"#ROUTE {self.layer},{self.dest},{self.source}\r"

    def handle_response(self, response: str):
        resp = self._parse_response(response)
        if not resp or resp.get('command') != "ROUTE":
           raise RuntimeError(f"Incorrect response '{resp.get('command')}' from Kramer device {resp.get('device')}" )
        params = resp['params'].split(',')
        msg =  f"Response from Kramer device {resp['device']}: {resp['command']}:" + os.linesep
        msg += f"  layer = {params[0]}" + os.linesep
        msg += f"  dest  = {params[1]}" + os.linesep
        msg += f"  src   = {params[2]}"
        return msg

# --- Context Manager Class ---

class KramerSocketConnection:
    """
    A context manager for managing the Kramer network socket connection.
    """
    def __init__(self, host: str, port: int, family: int = socket.AF_INET, type: int = socket.SOCK_STREAM):
        self.host = host
        self.port = port
        self.family = family
        self.type = type
        self.sock: Optional[socket.socket] = None
        print(f"[{host}:{port}] Initialized Kramer socket manager.")

    def __enter__(self) -> KramerProtocol:
        """
        Creates and connects the socket, then returns the KramerProtocol manager.
        """
        try:
            self.sock = socket.socket(self.family, self.type)
            print(f"[{self.host}:{self.port}] Kramer socket created.")
            print(f"[{self.host}:{self.port}] Attempting to connect to Kramer...")
            
            self.sock.settimeout(2.0) # Longer timeout for initial connect
            self.sock.connect((self.host, self.port))

            # Return the high-level manager instance
            return KramerProtocol(self.sock, self.host, self.port)
        
        except Exception as e:
            if self.sock:
                self.sock.close()
            print(f"[{self.host}:{self.port}] Kramer connection failed: {e}", file=sys.stderr)
            raise

    def __exit__(self, exc_type: Optional[type], exc_value: Optional[BaseException], traceback: Optional[Any]) -> bool:
        """
        Executed upon exiting the 'with' block. Ensures the socket is closed.
        """
        if self.sock:
            self.sock.close()
            print(f"[{self.host}:{self.port}] Kramer socket closed.")
        return False