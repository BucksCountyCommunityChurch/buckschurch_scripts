"""
SQ MIDI Listener

This script connects to an Allen & Heath SQ mixer, listens for specific
incoming MIDI Note On messages (triggered by SoftKeys), and then
executes a predefined sequence of commands.
"""

import time
import sys
from sq_midi_controller import (
    SocketConnection, 
    SQMidiProtocol,
    SQ_MIDI_PORT,
    RecallScene,
    SetMuteNRPN,
    SetFaderLevelNRPN,
    db_to_fader_level
)
# Import note constants from midi_notes.py
from midi_notes import (
    NOTE_C3, 
    NOTE_D3, 
    NOTE_CSHARP3
)

# --- !!! UPDATE THIS IP ADDRESS !!! ---
SQ_MIXER_IP = "192.168.7.158" 

# --- MIDI Note Definitions ---
NOTE_PRESET_C = NOTE_C3  # 48 (C3)
NOTE_PRESET_D = NOTE_D3  # 50 (D3)

# --- MIDI Channel to Listen On ---
# (Must match the channel your SoftKeys are set to transmit on)
MIDI_CHANNEL = 1 # Channel 1 (status byte 0x90)


def run_preset_C(controller: SQMidiProtocol):
    """
    Executes the command sequence for "Preset C"
    - Load Scene 1
    - Unmute Channel 1 to LR
    - Unmute the Main LR output
    - Set the level of Channel 1 to LR to 0dB
    - Mute channels 2-8 to LR
    """
    print("--- EXECUTING PRESET C ---")
    try:
        # 1. Load Scene 1
        controller.send_message(RecallScene(scene_number=1))
        # Give the mixer time to load the scene
        time.sleep(2.5) 
        
        # 2. Unmute Channel 1 to LR
        controller.send_message(SetMuteNRPN("IP1", "LR", mute_on=False))
        
        # 3. Unmute the Main LR output
        #    (Uses the new ("LR", "LR") mapping for the Master Mute)
        controller.send_message(SetMuteNRPN("LR", "LR", mute_on=False))
        
        # 4. Set Channel 1 to LR fader to 0dB
        fader_0db = db_to_fader_level(0.0)
        controller.send_message(SetFaderLevelNRPN("IP1", "LR", level=fader_0db))
        
        # 5. Mute channels 2-8 to LR
        for i in range(2, 9):
            controller.send_message(SetMuteNRPN(f"IP{i}", "LR", mute_on=True))
            
        print("--- PRESET C COMPLETE ---")
            
    except Exception as e:
        print(f"[PRESET C] Error: {e}", file=sys.stderr)


def run_preset_D(controller: SQMidiProtocol):
    """
    Executes the command sequence for "Preset D"
    - Load Scene 2
    - Unmute Channel 2 to LR
    - Unmute the Main LR output
    - Set the level of Channel 2 to LR to 0dB
    - Mute channels 1 and 3-8 to LR
    """
    print("--- EXECUTING PRESET D ---")
    try:
        # 1. Load Scene 2
        controller.send_message(RecallScene(scene_number=2))
        # Give the mixer time to load the scene
        time.sleep(2.5) 
        
        # 2. Unmute Channel 2 to LR
        controller.send_message(SetMuteNRPN("IP2", "LR", mute_on=False))
        
        # 3. Unmute the Main LR output
        controller.send_message(SetMuteNRPN("LR", "LR", mute_on=False))
        
        # 4. Set Channel 2 to LR fader to 0dB
        fader_0db = db_to_fader_level(0.0)
        controller.send_message(SetFaderLevelNRPN("IP2", "LR", level=fader_0db))
        
        # 5. Mute channels 1 and 3-8 to LR
        for i in [1] + list(range(3, 9)):
            controller.send_message(SetMuteNRPN(f"IP{i}", "LR", mute_on=True))
            
        print("--- PRESET D COMPLETE ---")
            
    except Exception as e:
        print(f"[PRESET D] Error: {e}", file=sys.stderr)


def parse_midi_message(data: bytes, controller: SQMidiProtocol):
    """
    Parses a raw byte buffer for MIDI Note On messages.
    """
    i = 0
    while i < len(data):
        # Look for a Status Byte
        if data[i] & 0x80: # Is the 8th bit set?
            
            # Check for Note On (0x9n) on our target channel
            status_byte_base = 0x90 + (MIDI_CHANNEL - 1)
            
            if data[i] == status_byte_base and i + 2 < len(data):
                note = data[i+1]
                velocity = data[i+2]
                
                # We only care about the "press" (velocity > 0)
                if velocity > 0:
                    print(f"\n[MIDI IN] Note On Received: Note={note} (0x{note:X}), Velocity={velocity}")
                    
                    # --- Trigger matching preset ---
                    if note == NOTE_PRESET_C:
                        run_preset_C(controller)
                    elif note == NOTE_PRESET_D:
                        run_preset_D(controller)
                    else:
                        print(f"[MIDI IN] Note {note} has no preset assigned.")
                    
                i += 3 # Move past this 3-byte message
            else:
                # Other message, skip it (we don't know its length, guess 1)
                i += 1
        else:
            # Not a status byte, must be running status or bad data
            i += 1


def main():
    """
    Main connection and listening loop.
    """
    print("--- Allen & Heath SQ MIDI Listener ---")
    while True: # Loop forever to reconnect if connection drops
        try:
            with SocketConnection(SQ_MIXER_IP, SQ_MIDI_PORT) as sq_controller:
                print(f"\nSuccessfully connected to {SQ_MIXER_IP}:{SQ_MIDI_PORT}.")
                print("Listening for MIDI notes... (Press CTRL-C to exit)")
                
                while True: # Main listening loop
                    try:
                        # Wait for a message to come in (with a timeout)
                        data = sq_controller.listen_blocking()
                        
                        if not data:
                            # This means a timeout occurred (data is None)
                            # or the connection was closed (data is b'').
                            # If connection closed, listen_blocking will raise
                            # an exception, so data is None here.
                            # We just continue to the next loop iteration.
                            continue 
                        
                        # If we get here, data is valid. Process the message.
                        parse_midi_message(data, sq_controller)
                        
                    except Exception as e:
                        print(f"Error in listen loop: {e}. Reconnecting...", file=sys.stderr)
                        break # Break inner loop to trigger reconnect
            
        except ConnectionRefusedError:
            print(f"\n--- CONNECTION FAILED ---")
            print(f"Could not connect to {SQ_MIXER_IP}:{SQ_MIDI_PORT}.")
            print("Please check IP, Port, and that MIDI over TCP/IP is enabled.")
            print("Retrying in 5 seconds...")
            time.sleep(5)
        except KeyboardInterrupt:
            # Catch CTRL-C here to exit gracefully
            print("\nShutdown signal (CTRL-C) received. Exiting.")
            sys.exit(0)
        except Exception as e:
            print(f"A critical error occurred: {e}. Restarting in 5 seconds...", file=sys.stderr)
            time.sleep(5)


if __name__ == "__main__":
    main()