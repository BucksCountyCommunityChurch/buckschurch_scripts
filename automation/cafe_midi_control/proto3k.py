"""
This file contains the Protocol 3000 logic for controlling
the Kramer device.
Updated with robust buffer handling to ignore delayed async messages.
"""

import socket
import time
import re
import os
import sys
from typing import Optional, Any

# Port is now defined in 'listener_config.yaml' and passed to KramerSocketConnection.

class KramerMessage:
    command="BASECLASS"
    # Updated Regex to be more robust with whitespace
    P3K_RESPONSE_RE = r"[~]([0-9])+[@](.*?) ((?:.*)[,]{0,1})\r\n"

    def get_command(self) -> str:
        raise NotImplementedError("get_command() not implemented")
    
    def get_response(self) -> str:
        return self.command

    def handle_response(self, response: str):
        raise NotImplementedError("handle_response() not implemented")

    def _parse_response(self, response: str) -> dict:
        match = re.search(KramerMessage.P3K_RESPONSE_RE, response)
        if not match:
            # It might be a simple response like "~01@ERR 003"
            return {}
            
        result = {
            'device': match.group(1),
            'command': match.group(2).strip(), # Strip whitespace
            'params': match.group(3).strip()
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

    def _recv_until_newline(self, timeout: float = 1.0) -> bytes:
        """
        Reads byte-by-byte until a newline \n is found or timeout occurs.
        This prevents reading multiple responses in one go.
        """
        self._sock.settimeout(timeout)
        data = b""
        start_time = time.time()
        
        while True:
            try:
                chunk = self._sock.recv(1)
                if not chunk:
                    break # Connection closed
                data += chunk
                if chunk == b'\n':
                    break
                if time.time() - start_time > timeout:
                    break
            except socket.timeout:
                break
        return data

    def send_message(self, msg: KramerMessage):
        """
        Sends a command and loops until it finds the MATCHING response.
        Ignores async notifications or delayed echoes from previous commands.
        """
        try:
            command_str = msg.get_command()
            data_bytes = command_str.encode('utf-8')
            
            # 1. Clear any old garbage currently in the buffer before sending
            self._sock.settimeout(0.01)
            try:
                while self._sock.recv(1024): pass
            except: pass

            # 2. Send the new command
            self._sock.sendall(data_bytes)
            print(f"[{self._host}:{self._port}] SENT: {command_str.strip()}")

            # 3. Read Loop: Keep reading lines until we find the matching command
            #    or we timeout (e.g. 2 seconds max wait)
            max_retries = 10
            found_match = False
            
            for _ in range(max_retries):
                data = self._recv_until_newline(timeout=0.5)
                if not data:
                    break
                
                decoded_line = data.decode('utf-8', errors='ignore')
                
                # Parse this line
                parsed = msg._parse_response(decoded_line)
                
                if not parsed:
                    # Could not parse this line, might be noise or error
                    continue

                rx_cmd = parsed.get('command', '').upper()
                expected_rx_cmd = msg.get_response().upper()

                if rx_cmd == expected_rx_cmd:
                    # SUCCESS: We found the response for the command we sent
                    print(f"[{self._host}:{self._port}] RECV (MATCH): {decoded_line.strip()}")
                    resp_msg = msg.handle_response(decoded_line)
                    if resp_msg:
                        print(f"[{self._host}:{self._port}] {resp_msg}")
                    found_match = True
                    break
                else:
                    # MISMATCH: This is likely a delayed response from a previous command
                    print(f"[{self._host}:{self._port}] RECV (IGNORED): {decoded_line.strip()} (Expected {expected_rx_cmd})")

            if not found_match:
                 print(f"[{self._host}:{self._port}] Warning: Timed out waiting for response to {msg.command}")

        except Exception as ex:
            print(f"[{self._host}:{self._port}] Error Sending Kramer command: {ex!r}")
        
        time.sleep(0.1)


class Handshake(KramerMessage):
    def __init__(self):
        self.command="Handshake"

    def get_command(self) -> str:
        return "#\r"
    
    def get_response(self):
        return ""
        
    def handle_response(self, response: str):
        # The handshake response format can vary, we just check for OK if parsable
        resp = self._parse_response(response)
        if resp and resp.get('params') == 'OK':
             return f"Response from Kramer device {resp['device']}: Handshake OK"
        return "Handshake response received."


class Route(KramerMessage):
    LAYER_VIDEO=1
    LAYER_USB=5
    def __init__(self, source: int, dest: int = 1, layer: int = LAYER_VIDEO):
        self.command="ROUTE"
        self.layer = layer
        self.dest = dest
        self.source = int(source)
    
    def get_command(self) -> str:
        return f"#{self.command} {self.layer},{self.dest},{self.source}\r"

    def handle_response(self, response: str):
        resp = self._parse_response(response)
        # We rely on the send_message loop to match the command name,
        # so here we just format the output.
        if not resp: return None
        
        params = resp['params'].split(',')
        if len(params) < 3: return f"Raw Route Response: {response}"

        msg =  f"Response from Kramer device {resp['device']}: {resp['command']}:" + os.linesep
        msg += f"  layer = {params[0]}" + os.linesep
        msg += f"  dest  = {params[1]}" + os.linesep
        msg += f"  src   = {params[2]}"
        return msg

class VideoMute(KramerMessage):
    VMUTE_ENABLE=0
    VMUTE_DISABLE=1
    VMUTE_BLANK=2

    def __init__(self, dest: int = 1, flag: int=VMUTE_ENABLE):
        self.command="VMUTE"
        self.dest = dest
        self.flag = flag
    
    def get_command(self) -> str:
        return f"#{self.command} {self.dest},{self.flag}\r"

    def handle_response(self, response: str):
        resp = self._parse_response(response)
        # We rely on the send_message loop to match the command name,
        # so here we just format the output.
        if not resp: return None
        
        params = resp['params'].split(',')
        if len(params) < 2: return f"Raw Route Response: {response}"

        msg =  f"Response from Kramer device {resp['device']}: {resp['command']}:" + os.linesep
        msg += f"  dest  = {params[0]}" + os.linesep
        msg += f"  flag  = {params[1]}"
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