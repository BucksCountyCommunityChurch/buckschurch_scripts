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

# --- FADER TAPER MAPPING ---
# This map is based on the 14-bit MIDI Level derived from the VA (MSB) and VF (LSB)
# columns of the SQ Mixer's fader taper table, as provided by the user.
# Level (14-bit) = (VA (7-bit) << 7) | VF (7-bit)
# Linear interpolation is used between these discrete points for precision.
FADER_TAPER_MAP = [
    #   DB,    Level (14-bit integer)
    (-80.0, 5698),   # 0x2C42
    (-60.0, 8073),   # 0x3F09
    (-40.0, 10447),  # 0x514F
    (-35.0, 11041),  # 0x5621
    (-30.0, 11634),  # 0x5A72
    (-25.0, 12228),  # 0x5F44
    (-20.0, 12822),  # 0x6416
    (-15.0, 13415),  # 0x6867
    (-10.0, 14009),  # 0x6D39
    (-5.0, 14602),   # 0x720A
    (0.0, 15196),    # 0x765C (Unity)
    (5.0, 15790),    # 0x7B2E
    (10.0, 16383)    # 0x7F7F (Max Level)
]

# --- Helper functions for conversion ---

def db_to_fader_level(db: float) -> int:
    """
    Converts a dB value to the 14-bit MIDI level (0-16383) using the
    custom fader taper map. Linear interpolation is used between the 
    discrete data points provided by the user.
    """
    # 1. Handle clipping/out-of-range values
    
    # +10dB is the max
    if db >= 10.0:
        return 16383 
    
    # Treat anything below -80dB as -Inf (0x0000)
    if db <= -80.0:
        return 0 
        
    # 2. Find the two adjacent points for interpolation
    
    # We loop through the map to find the segment (p1, p2) where p1.DB <= db < p2.DB
    p1_db, p1_level = FADER_TAPER_MAP[0] 
    p2_db, p2_level = FADER_TAPER_MAP[0]
    
    for i in range(1, len(FADER_TAPER_MAP)):
        db_curr, level_curr = FADER_TAPER_MAP[i]
        
        if db <= db_curr:
            # Found the segment: p1 is the previous point, p2 is the current point
            p2_db, p2_level = FADER_TAPER_MAP[i]
            p1_db, p1_level = FADER_TAPER_MAP[i-1]
            break
    
    # 3. Perform linear interpolation
    
    # This check prevents division by zero, although the map points are distinct
    if p2_db == p1_db:
        return p1_level

    # Interpolation formula: y = y1 + (x - x1) * (y2 - y1) / (x2 - x1)
    fader_level = p1_level + (db - p1_db) * (p2_level - p1_level) / (p2_db - p1_db)
    
    # Round to the nearest integer and ensure it stays within the 14-bit range (0-16383)
    return int(max(0, min(16383, round(fader_level))))


def pan_to_value(pan: float) -> int:
    """
    Converts a Pan/Balance value (-100.0 to +100.0) to the 14-bit MIDI level (0-16383).
    -100.0 (L100%) = 0
    0.0 (Center)   = 8192 (0x2000)
    +100.0 (R100%) = 16383 (0x3FFF)
    """
    if pan < -100.0: pan = -100.0
    if pan > 100.0: pan = 100.0
    
    # Scale from [-100, 100] to [0, 16383]
    # (pan + 100) / 200 = 0 to 1 scaling
    # Value = scaled_pan * 16383
    
    # Note: 8192 is half of 16384. This formula should be close enough.
    return int(((pan + 100.0) / 200.0) * 16383)


def build_nrpn_sequence(midi_channel_idx: int, nrpn_address: int, nrpn_value: int) -> List[bytes]:
    """
    Generates the four-message MIDI Non-Registered Parameter Number (NRPN) sequence.
    This is the core communication method for fader, pan, mute, and assign.
    
    :param midi_channel_idx: 0-15 (for MIDI Channel 1-16)
    :param nrpn_address: The 14-bit channel/control address (0-16383)
    :param nrpn_value: The 14-bit control value (0-16383)
    :return: A list of four raw MIDI messages as bytes objects.
    """
    
    # 14-bit values are split into 7-bit MSB (Most Significant Byte) and LSB (Least Significant Byte)
    
    # NRPN Address (Parameter Number)
    nrpn_address_msb = (nrpn_address >> 7) & 0x7F # Bits 14-7
    nrpn_address_lsb = nrpn_address & 0x7F       # Bits 6-0

    # NRPN Value (Data Entry)
    nrpn_value_msb = (nrpn_value >> 7) & 0x7F     # Bits 14-7
    nrpn_value_lsb = nrpn_value & 0x7F           # Bits 6-0
    
    # Status byte for Control Change (CC) is 0xB0 + MIDI Channel Index
    status_byte = 0xB0 | midi_channel_idx

    # Message 1: NRPN MSB (CC 99 / 0x63)
    msg1 = bytes([status_byte, 0x63, nrpn_address_msb])
    
    # Message 2: NRPN LSB (CC 98 / 0x62)
    msg2 = bytes([status_byte, 0x62, nrpn_address_lsb])
    
    # Message 3: Data Entry MSB (CC 6 / 0x06)
    msg3 = bytes([status_byte, 0x06, nrpn_value_msb])
    
    # Message 4: Data Entry LSB (CC 38 / 0x26)
    msg4 = bytes([status_byte, 0x26, nrpn_value_lsb])

    # Note: The SQ manual says to send the LSB (CC 38) as the last command.
    return [msg1, msg2, msg3, msg4]


# --- Socket/Protocol Classes (Unchanged) ---
class SocketConnection:
    """
    Context Manager for establishing and cleanly closing the TCP socket connection.
    Usage: with SocketConnection(host, port) as protocol: ...
    """
    def __init__(self, host: str, port: int, family: int = socket.AF_INET, type: int = socket.SOCK_STREAM):
        self.host = host
        self.port = port
        self.family = family
        self.type = type
        self.sock: Optional[socket.socket] = None
        print(f"[{host}:{port}] Initialized SQ socket manager.")

    def __enter__(self) -> 'SQMidiProtocol':
        """
        Creates and connects the socket, then returns the SQMidiProtocol manager.
        """
        try:
            self.sock = socket.socket(self.family, self.type)
            print(f"[{self.host}:{self.port}] SQ socket created.")
            print(f"[{self.host}:{self.port}] Attempting to connect to SQ Mixer...")
            
            # Use a short timeout for connection since it's local
            self.sock.settimeout(2.0) 
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(0.5) # Reset to short timeout for listening
            
            # Return the high-level manager instance
            return SQMidiProtocol(self.sock, self.host, self.port)
        
        except Exception as e:
            if self.sock:
                self.sock.close()
            print(f"[{self.host}:{self.port}] SQ connection failed: {e!r}", file=sys.stderr)
            raise

    def __exit__(self, exc_type: Optional[type], exc_value: Optional[BaseException], traceback: Optional[Any]) -> bool:
        """
        Executed upon exiting the 'with' block. Ensures the socket is closed.
        """
        if self.sock:
            self.sock.close()
            print(f"[{self.host}:{self.port}] SQ socket closed.")
        # Returning False re-raises any exception that occurred inside the 'with' block
        return False


class SQMidiProtocol:
    """
    A wrapper class that provides command passing over an established SQ connection.
    """
    def __init__(self, sock: socket.socket, host: str, port: int):
        self._sock = sock
        self._host = host
        self._port = port
        print(f"[{host}:{port}] SQ Protocol manager initialized.")

    def listen_blocking(self) -> Optional[bytes]:
        """
        Blocks until data is received or the socket times out.
        Returns the received raw bytes.
        """
        try:
            # We don't expect responses, only incoming MIDI data (like SoftKeys)
            data = self._sock.recv(1024)
            if data:
                # print(f"[{self._host}:{self._port}] RECV: {data.hex()}")
                return data
            return None
        except socket.timeout:
            return None
        except Exception as ex:
            print(f"[{self._host}:{self._port}] Error during listen: {ex!r}", file=sys.stderr)
            raise # Re-raise to trigger connection restart

    def send_message(self, msg: 'SQMidiMessage'):
        """
        Sends a sequence of MIDI commands (bytes) to the SQ mixer.
        """
        try:
            # All SQMidiMessages define get_command() to return a list of bytes
            commands = msg.get_command()
            
            # Send each message byte array individually
            for command in commands:
                self._sock.sendall(command)
                # print(f"[{self._host}:{self._port}] SENT: {command.hex()}")
                # Brief pause between messages to prevent overwhelming the mixer
                time.sleep(0.005) 
            
            print(f"[{self._host}:{self._port}] Command SENT: {msg.command} ({len(commands)} messages)")

        except Exception as ex:
            print(f"[{self._host}:{self._port}] Error Sending SQ command: {ex!r}", file=sys.stderr)


# --- Message Classes ---
class SQMidiMessage:
    command="BASECLASS"
    
    def get_command(self) -> List[bytes]:
        raise NotImplementedError("get_command() not implemented")


class RecallScene(SQMidiMessage):
    """
    Recalls a Scene.
    Uses Program Change (PC) and Bank Select (BS).
    """
    def __init__(self, scene_number: int, midi_channel: int = 1):
        if not (1 <= midi_channel <= 16):
            raise ValueError("MIDI channel must be 1-16.")
            
        self.command = f"RecallScene ({scene_number})"
        self.scene_number = scene_number
        self.midi_channel_idx = midi_channel - 1
        
        # The SQ uses Bank LSB (CC 32) to select the Scene Bank (Bank 0 is Mix Mode)
        # It then uses Program Change (PC) to select the scene.
        # Bank MSB (CC 0) is typically used for a larger address space, but SQ seems to use it as 0x00.
        
        # Scene number mapping:
        # Scene 1 is PC 0
        # Scene 99 is PC 98
        self.program_change = scene_number - 1
        
        # Fixed Bank Select MSB (CC 0 / 0x00) and LSB (CC 32 / 0x00) for regular scenes
        self.bank_select_msb = 0x00 
        self.bank_select_lsb = 0x00 

    def get_command(self) -> List[bytes]:
        """Generates the Bank Select and Program Change sequence."""
        status_byte = 0xB0 | self.midi_channel_idx
        program_change_status = 0xC0 | self.midi_channel_idx
        
        # Message 1: Bank Select MSB (CC 0)
        msg1 = bytes([status_byte, 0x00, self.bank_select_msb])
        
        # Message 2: Bank Select LSB (CC 32 / 0x20)
        msg2 = bytes([status_byte, 0x20, self.bank_select_lsb])
        
        # Message 3: Program Change
        msg3 = bytes([program_change_status, self.program_change])
        
        return [msg1, msg2, msg3]


class SetMuteNRPN(SQMidiMessage):
    """
    Sets the Mute status of a channel crosspoint.
    Control Type: Mute (Base Address 0x0000)
    Value: 0 (Unmute/Off), 1 (Mute/On)
    """
    def __init__(self, from_ch: str, to_ch: str, mute_on: bool, midi_channel: int = 1):
        """
        Initializes the mute command.
        :param mute_on: The mute state (True for Mute On, False for Mute Off).
        """
        if not (1 <= midi_channel <= 16):
            raise ValueError("MIDI channel must be 1-16.")
            
        self.command = f"SetMute ({(from_ch, to_ch)} -> {'ON' if mute_on else 'OFF'})"
        self.midi_channel_idx = midi_channel - 1
        
        # 1. Get the NRPN Address from the database
        self.nrpn_address = sq_midi_db.get_nrpn_address("Mute", from_ch, to_ch)
        
        # 2. Set the NRPN Value (Mute uses the LSB only)
        # Note: The SQ uses the 14-bit NRPN data field, but for mute the LSB holds the 0/1 state.
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
    Sets the Fader/Send level of a channel crosspoint.
    Control Type: Fader (Base Address 0x4000)
    Value: 14-bit level (0 to 16383)
    """
    def __init__(self, from_ch: str, to_ch: str, level: int, midi_channel: int = 1):
        """
        Initializes the fader level command.
        :param level: The 14-bit fader level (0-16383). Use db_to_fader_level() to convert from dB.
        """
        if not (1 <= midi_channel <= 16):
            raise ValueError("MIDI channel must be 1-16.")
        if not (0 <= level <= 16383):
             print(f"Warning: Fader level {level} outside 0-16383 range. Clamping.", file=sys.stderr)
             level = max(0, min(16383, level))
            
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
    Sets the Pan/Balance level of a channel crosspoint.
    Control Type: Pan (Base Address 0x5000)
    Value: 14-bit level (0-16383)
    """
    def __init__(self, from_ch: str, to_ch: str, pan_value: int, midi_channel: int = 1):
        """
        Initializes the pan command.
        :param pan_value: The 14-bit pan value (0-16383). Use pan_to_value() to convert from float.
        """
        if not (1 <= midi_channel <= 16):
            raise ValueError("MIDI channel must be 1-16.")
        if not (0 <= pan_value <= 16383):
             print(f"Warning: Pan value {pan_value} outside 0-16383 range. Clamping.", file=sys.stderr)
             pan_value = max(0, min(16383, pan_value))
            
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
        
        # 2. Set the NRPN Value
        self.nrpn_value = 1 if assign_on else 0

    def get_command(self) -> List[bytes]:
        """Generates the 4-message NRPN sequence."""
        return build_nrpn_sequence(
            self.midi_channel_idx, 
            self.nrpn_address, 
            self.nrpn_value
        )