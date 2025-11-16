import socket
import time
import os
import sys
from typing import Optional, Any, List

# Import the new database file
import sq_midi_db

# --- IMPORTANT ---
# Port is now defined in 'presets.yaml' and passed to SocketConnection.
# Removed: SQ_MIDI_PORT = 51325


# --- Helper functions for conversion ---

def db_to_fader_level(db: float) -> int:
    """
    Converts a dB value to the 14-bit MIDI level (0-16383).
    Based on the taper in Reference.csv:
    +10dB = 16383
    0dB   = 12288
    -10dB = 8192
    -30dB = 4096
    -inf  = 0
    """
    # Clip to max/min range
    if db > 10.0: db = 10.0
    if db < -90.0: return 0 # Treat anything below -90dB as -inf (0)
    
    if db > 0.0:
        # +10dB to 0dB range (16383 to 12288)
        return int(12288 + (db / 10.0) * (16383 - 12288))
    elif db > -10.0:
        # 0dB to -10dB range (12288 to 8192)
        return int(8192 + ((db + 10.0) / 10.0) * (12288 - 8192))
    elif db > -30.0:
        # -10dB to -30dB range (8192 to 4096)
        return int(4096 + ((db + 30.0) / 20.0) * (8192 - 4096))
    else:
        # -30dB to -90dB range (4096 to 0) - rough linear guess for the log taper
        return int(0 + ((db + 90.0) / 60.0) * 4096)

def pan_to_value(pan: float) -> int:
    """
    Converts a pan value (-100 to +100, where 0 is center) to the 14-bit MIDI value (0-16383).
    -100 = 0 (Left)
    0    = 8192 (Center)
    +100 = 16383 (Right)
    """
    if pan < -100.0: pan = -100.0
    if pan > 100.0: pan = 100.0
    
    # Scale -100 to +100 range to 0 to 16383
    return int(((pan + 100.0) / 200.0) * 16383)


class SQMidiMessage:
    """
    Base class for all SQ MIDI commands.
    """
    command = "BASECLASS"

    def get_command(self) -> List[bytes]:
        """
        Returns a list of raw MIDI message bytes to be sent to the mixer.
        Raises NotImplementedError if not overridden.
        """
        raise NotImplementedError("get_command() not implemented")

    def handle_response(self, response: bytes):
        """
        Handles any immediate response bytes from the mixer.
        """
        # By default, do nothing with a response.
        pass


def build_nrpn_sequence(midi_channel: int, nrpn_address: int, nrpn_value: int) -> List[bytes]:
    """
    Helper function to construct the standard 4-message NRPN sequence.
    :param midi_channel: 0-15 (0 for Channel 1, etc.)
    :param nrpn_address: The 14-bit address (0-16383) of the control.
    :param nrpn_value: The 14-bit value (0-16383) to set the control to.
    :return: A list of 4 raw bytes messages.
    """
    # Split 14-bit Address and Value into 7-bit MSB/LSB
    addr_msb = (nrpn_address >> 7) & 0x7F
    addr_lsb = nrpn_address & 0x7F
    val_msb = (nrpn_value >> 7) & 0x7F
    val_lsb = nrpn_value & 0x7F
    
    # Status byte for CC messages on the correct channel
    status_byte = 0xB0 + midi_channel
    
    # 1. NRPN Address MSB (CC #99)
    msg1 = bytes([status_byte, 99, addr_msb])
    
    # 2. NRPN Address LSB (CC #98)
    msg2 = bytes([status_byte, 98, addr_lsb])
    
    # 3. Data Entry MSB (CC #6)
    msg3 = bytes([status_byte, 6, val_msb])
    
    # 4. Data Entry LSB (CC #38)
    msg4 = bytes([status_byte, 38, val_lsb])
    
    return [msg1, msg2, msg3, msg4]


class SQMidiProtocol:
    """
    Manages the TCP/IP connection and sending/receiving of MIDI messages.
    """
    def __init__(self, sock: socket.socket, host: str, port: int):
        self._sock = sock
        self._host = host
        self._port = port
        print(f"[{host}:{port}] SQ MIDI Protocol manager initialized.")

    def send_message(self, msg: SQMidiMessage):
        """
        Sends a sequence of MIDI messages corresponding to the command.
        """
        try:
            # 1. Get the list of raw bytes from the message class.
            command_list = msg.get_command()
            
            # (Ensure it's a list for iteration)
            if not isinstance(command_list, list):
                command_list = [command_list] # Wrap single message in list

            print(f"[{self._host}:{self._port}] {msg.command} sending {len(command_list)} message(s)...")

            # 2. Iterate and publish each message to the socket.
            for i, data_bytes in enumerate(command_list):
                self._sock.sendall(data_bytes)
                print(f"  [{self._host}:{self._port}] Sent message {i+1}/{len(command_list)} (len={len(data_bytes)}): {data_bytes.hex(' ')}")

                # 3. Handle MIDI responses (if any).
                try:
                    self._sock.settimeout(0.02) # Very short timeout for sequential messages
                    data = self._sock.recv(1024)
                    if data:
                        print(f"  [{self._host}:{self._port}] Response Received: (len={len(data)}): {data.hex(' ')}")
                        msg.handle_response(data)
                except socket.timeout:
                    # This is the normal/expected case when expecting no immediate response
                    pass
                
                # Short pause between messages in a sequence
                if len(command_list) > 1:
                    time.sleep(0.01) # Small delay to ensure mixer processes messages sequentially
            
            print(f"[{self._host}:{self._port}] {msg.command} sequence complete.")

        except Exception as ex:
            print(f"[{self._host}:{self._port}] Error sending command '{msg.command}': {ex}", file=sys.stderr)
        
        # Reset timeout for the main connection manager
        finally:
            self._sock.settimeout(0.5) 
            time.sleep(0.05) # Give the mixer a moment to process before next command

    def listen_blocking(self) -> bytes:
        """
        Sets the socket to blocking mode and waits to receive data.
        Returns the raw bytes received.
        """
        try:
            # Set a short timeout (e.g., 0.5 seconds) so the loop
            # can be interrupted by a KeyboardInterrupt
            self._sock.settimeout(0.5) 
            data = self._sock.recv(1024)
            return data
        except socket.timeout:
            # This is expected if no data arrives in 0.5s
            # Return None to signal the main loop to continue
            return None
        except Exception as e:
            print(f"[{self._host}:{self._port}] Error while listening: {e}", file=sys.stderr)
            # Re-raise to break the loop
            raise


class SocketConnection:
    """
    Context Manager for establishing and cleanly closing the TCP socket connection.
    Usage: with SocketConnection(host, port) as protocol: ...
    """
    def __init__(self, host: str, port: int, family: int = socket.AF_INET, type: int = socket.SOCK_STREAM):
        self._host = host
        self._port = port
        self._family = family
        self._type = type
        self.sock: Optional[socket.socket] = None
        print(f"[{host}:{port}] Initialized socket connection manager.")

    def __enter__(self) -> SQMidiProtocol:
        """
        Connects the socket and returns the SQMidiProtocol object.
        """
        try:
            self.sock = socket.socket(self._family, self._type)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            print(f"[{self._host}:{self._port}] Attempting to connect...")
            self.sock.settimeout(2.0) # Give more time for initial connect
            self.sock.connect((self._host, self._port))
            # Return the new SQMidiProtocol manager
            return SQMidiProtocol(self.sock, self._host, self._port)

        except Exception as e:
            if self.sock:
                self.sock.close()
            print(f"[{self._host}:{self._port}] Connection failed: {e}", file=sys.stderr)
            raise

    def __exit__(self, exc_type: Optional[type], exc_value: Optional[BaseException], traceback: Optional[Any]) -> bool:
        """
        Closes the socket when exiting the 'with' block.
        """
        if self.sock:
            self.sock.close()
            print(f"[{self._host}:{self._port}] Connection closed.")
        
        # If an exception occurred, we want to re-raise it
        if exc_value:
            return False
        return True


# --- SQ MIDI MESSAGE IMPLEMENTATIONS ---

class RecallScene(SQMidiMessage):
    """
    Sends MIDI Bank Select (CC 0, CC 32) and Program Change (PC)
    messages to recall a scene (1-300).
    
    This logic is based on the "Scene" example in Generator.csv.
    """
    def __init__(self, scene_number: int, midi_channel: int = 1):
        if not (1 <= scene_number <= 300):
            raise ValueError("Scene number must be 1-300.")
        if not (1 <= midi_channel <= 16):
            raise ValueError("MIDI channel must be 1-16.")
            
        self.command = f"RecallScene (Scene {scene_number})"
        
        # Scene index is 0-299
        scene_idx = scene_number - 1
        
        # Scene 1-128 = Bank 0, Program 0-127
        # Scene 129-256 = Bank 1, Program 0-127
        # Scene 257-300 = Bank 2, Program 0-43
        self.bank = scene_idx // 128
        self.program = scene_idx % 128
        self.midi_channel_idx = midi_channel - 1 # 0-indexed for status byte

    def get_command(self) -> List[bytes]:
        """
        Generates the Bank Select + Program Change byte sequence.
        """
        # Status bytes
        cc_status = 0xB0 + self.midi_channel_idx
        pc_status = 0xC0 + self.midi_channel_idx
        
        # Bank is a 14-bit value, but the SQ only uses Bank MSB (CC 0)
        # for the high byte, and LSB (CC 32) for the low byte.
        # SQ uses Bank: 0/1/2 for 1-128/129-256/257-300
        bank_msb = 0x00
        bank_lsb = self.bank
        
        # Message 1: Bank Select MSB (CC 0)
        msg1 = bytes([cc_status, 0, bank_msb])
        # Message 2: Bank Select LSB (CC 32)
        msg2 = bytes([cc_status, 32, bank_lsb])
        # Message 3: Program Change
        msg3 = bytes([pc_status, self.program])
        
        return [msg1, msg2, msg3]


class SetMuteNRPN(SQMidiMessage):
    """
    Sets the mute status of a channel crosspoint (e.g., IP1 -> LR) or a master channel (e.g., LR Master).
    Control Type: Mute (Base Address 0x0000)
    Value: 0 (Off), 1 (On)
    """
    def __init__(self, from_ch: str, to_ch: str, mute_on: bool, midi_channel: int = 1):
        if not (1 <= midi_channel <= 16):
            raise ValueError("MIDI channel must be 1-16.")
            
        self.command = f"SetMute ({(from_ch, to_ch)} -> {'ON' if mute_on else 'OFF'})"
        self.midi_channel_idx = midi_channel - 1 # 0-indexed
        
        # 1. Get the NRPN Address from the database
        self.nrpn_address = sq_midi_db.get_nrpn_address("Mute", from_ch, to_ch)
        
        # 2. Set the NRPN Value (0 or 1)
        self.nrpn_value = 1 if mute_on else 0

    def get_command(self) -> List[bytes]:
        """Generates the 4-message NRPN sequence."""
        return build_nrpn_sequence(
            self.midi_channel_idx, 
            self.nrpn_address, 
            self.nrpn_value
        )


class SetFaderLevelNRPN(SQMidiMessage):
    """
    Sets the fader level of a channel crosspoint or a master channel.
    Control Type: Fader (Base Address 0x4000)
    Value: 14-bit (0-16383)
    """
    def __init__(self, from_ch: str, to_ch: str, level: int, midi_channel: int = 1):
        """
        Initializes the fader level command.
        :param level: The fader level (0-16383). Use db_to_fader_level() helper.
        """
        if not (0 <= level <= 16383):
            raise ValueError("MIDI level must be 0-16383 (14-bit).")
        if not (1 <= midi_channel <= 16):
            raise ValueError("MIDI channel must be 1-16.")
        
        self.command = f"SetFaderLevel ({(from_ch, to_ch)} -> {level})"
        self.midi_channel_idx = midi_channel - 1
        
        # 1. Get the NRPN Address from the database
        self.nrpn_address = sq_midi_db.get_nrpn_address("Fader", from_ch, to_ch)
        
        # 2. Set the NRPN Value
        self.nrpn_value = level

    def get_command(self) -> List[bytes]:
        """Generates the 4-message NRPN sequence."""
        return build_nrpn_sequence(
            self.midi_channel_idx, 
            self.nrpn_address, 
            self.nrpn_value
        )


class SetPanNRPN(SQMidiMessage):
    """
    Sets the Pan/Balance of a channel crosspoint or a master channel.
    Control Type: Pan (Base Address 0x5000)
    Value: 14-bit (0-16383)
    """
    def __init__(self, from_ch: str, to_ch: str, pan_value: int, midi_channel: int = 1):
        """
        Initializes the pan command.
        :param pan_value: The pan value (0-16383). Use pan_to_value() helper.
        """
        if not (0 <= pan_value <= 16383):
            raise ValueError("Pan value must be 0-16383 (14-bit).")
        if not (1 <= midi_channel <= 16):
            raise ValueError("MIDI channel must be 1-16.")
        
        self.command = f"SetPan ({(from_ch, to_ch)} -> {pan_value})"
        self.midi_channel_idx = midi_channel - 1
        
        # 1. Get the NRPN Address from the database
        self.nrpn_address = sq_midi_db.get_nrpn_address("Pan", from_ch, to_ch)
        
        # 2. Set the NRPN Value
        self.nrpn_value = pan_value

    def get_command(self) -> List[bytes]:
        """Generates the 4-message NRPN sequence."""
        return build_nrpn_sequence(
            self.midi_channel_idx, 
            self.nrpn_address, 
            self.nrpn_value
        )


class SetAssignNRPN(SQMidiMessage):
    """
    Sets the Group/Mix Assign status of a channel crosspoint.
    Control Type: Assign (Base Address 0x6000)
    Value: 0 (Off), 1 (On)
    """
    def __init__(self, from_ch: str, to_ch: str, assign_on: bool, midi_channel: int = 1):
        """
        Initializes the assign command.
        :param assign_on: The assign state (True for On, False for Off).
        """
        if not (1 <= midi_channel <= 16):
            raise ValueError("MIDI channel must be 1-16.")
            
        self.command = f"SetAssign ({(from_ch, to_ch)} -> {'ON' if assign_on else 'OFF'})"
        self.midi_channel_idx = midi_channel - 1
        
        # 1. Get the NRPN Address from the database
        self.nrpn_address = sq_midi_db.get_nrpn_address("Assign", from_ch, to_ch)
        
        # 2. Set the NRPN Value (0 or 1)
        self.nrpn_value = 1 if assign_on else 0

    def get_command(self) -> List[bytes]:
        """Generates the 4-message NRPN sequence."""
        return build_nrpn_sequence(
            self.midi_channel_idx, 
            self.nrpn_address, 
            self.nrpn_value
        )