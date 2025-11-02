import socket
import time
import re
import os
import sys
from typing import Optional, Any

PROTO3K_PORT = 5000


class Proto3kMessage:
    command="BASECLASS"
    P3K_RESPONSE_RE = "[~]([0-9])+[@](.*) ((?:.*)[,]{0,1})\r\n"

    def get_command(self) -> str:
        raise NotImplementedError("get_command() not implemented")
    
    def handle_response(self, response: str):
        raise NotImplementedError("get_command() not implemented")

    def _parse_response(self, response: str) -> dict:
        match = re.search(Proto3kMessage.P3K_RESPONSE_RE, response)
        result = {
            'device': match.group(1),
            'command': match.group(2),
            'params': match.group(3)
        }
        return result

class Protocol3k:
    """
    A wrapper class that provides Kramer Protocol 3000 command
    passing over an estalished connection.

    This object is returned by SocketConnection.__enter__.
    """
    def __init__(self, sock: socket.socket, host: str, port: int):
        self._sock = sock
        self._host = host
        self._port = port
        print(f"[{host}:{port}] Protocol 3000 manager initialized on connected socket.")

        self.send_message(Handshake())

    def send_message(self, msg: Proto3kMessage):
        """
        Converts the string message to a bytearray and sends it over the socket.
        Sockets require data to be in bytes or bytearray format.
        """
        try:
            command = msg.get_command()
            # 1. Convert the string to bytes using a standard encoding (UTF-8 is recommended).
            data_bytes = command.encode('utf-8')

            # 2. Convert the bytes object into a modifiable bytearray (as requested).
            # Note: If no modification is needed, using the bytes object directly is faster.
            data_bytearray = bytearray(data_bytes)
        
            # 3. Publish data to sucket
            self._sock.sendall(data_bytearray)
            print(f"[{self._host}:{self._port}] {msg.command} sent(len={len(data_bytearray)}): {data_bytearray!r}")

            # 4. Receive the response message
            data = self._sock.recv(1024)
            print(f"[{self._host}:{self._port}] Response Received: {data}")

            # 5. Handle the response and log the handler output
            resp_msg = msg.handle_response(data)
            if resp_msg:
                print(f"[{self._host}:{self._port}] {resp_msg}")
        except Exception as ex:
            print("Error Sending command ", repr(ex))
        time.sleep(0.5)


class Handshake(Proto3kMessage):
    def __init__(self):
        self.command="Handshake"

    def get_command(self) -> str:
        return "#\r"
    def handle_response(self, response: str):
        resp = self._parse_response(response)
        if resp['params'] != 'OK':
           raise RuntimeError(f"Unable to establish interface with device {resp['device']}")
        return f"Response from device {resp['device']}: Handshake OK"


class Route(Proto3kMessage):
    LAYER_VIDEO=1
    LAYER_USB=5
    def __init__(self,source: int):
        self.command="Route"
        self.layer=Route.LAYER_VIDEO
        self.dest=1
        self.source=source
    
    def get_command(self) -> str:
        return "#ROUTE\ {self.layer},{self.dest},{self.source}\r"

    def handle_response(self, response: str):
        resp = self._parse_response(response)
        if resp['command'] != "ROUTE":
            raise RuntimeError(f"Incorrect response '{resp['command']} from device {resp['device']}" )
        params=resp['params'].split(',')
        msg =  f"Response from device {resp['device']}: {resp['command']}:" + os.linesep
        msg += f" layer = {params[0]}" + os.linesep
        msg += f" dest  = {params[1]}" + os.linesep
        msg += f" src   = {params[2]}"
        return msg

# --- Context Manager Class ---

class SocketConnection:
    """
    A context manager for managing a network socket connection lifecycle.

    It ensures the low-level socket is properly created on entry and closed on exit.
    It returns a high-level SocketManager instance for interaction.
    """
    def __init__(self, host: str, port: int, family: int = socket.AF_INET, type: int = socket.SOCK_STREAM):
        """
        Initializes the context manager with connection parameters.
        """
        self.host = host
        self.port = port
        self.family = family
        self.type = type
        self.sock: Optional[socket.socket] = None
        print(f"[{host}:{port}] Initialized socket connection manager.")

    def __enter__(self) -> Protocol3k:
        """
        Executed upon entering the 'with' block.
        Creates and attempts to connect the socket, then returns the manager.

        Returns:
            A SocketManager object wrapping the connected socket.
        """
        try:
            # 1. Create the socket
            self.sock = socket.socket(self.family, self.type)
            print(f"[{self.host}:{self.port}] Socket created successfully.")

            # 2. Attempt to connect (Mocked for sandbox environment)
            print(f"[{self.host}:{self.port}] Attempting to connect...")
            
            self.sock.settimeout(0.5)
            self.sock.connect((self.host, self.port))

            # 3. Return the high-level manager instance
            return Protocol3k(self.sock, self.host, self.port)
        
        except Exception as e:
            # Clean up the socket if creation/connection failed before returning
            if self.sock:
                self.sock.close()
            print(f"[{self.host}:{self.port}] Connection failed: {e}", file=sys.stderr)
            # Re-raise the exception
            raise

    def __exit__(self, exc_type: Optional[type], exc_value: Optional[BaseException], traceback: Optional[Any]) -> bool:
        """
        Executed upon exiting the 'with' block. Ensures the socket is closed.
        """
        if self.sock:
            # Close the low-level socket gracefully
            self.sock.close()
            print(f"[{self.host}:{self.port}] Socket closed successfully.")
        
        # Return False to re-raise any exception that occurred inside the 'with' block
        return False

