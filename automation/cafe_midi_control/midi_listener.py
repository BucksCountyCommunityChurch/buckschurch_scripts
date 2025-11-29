"""
SQ/Kramer MIDI Listener

This script connects to an Allen & Heath SQ mixer and a Kramer video switcher.
It listens for incoming MIDI Note On messages (triggered by SQ SoftKeys)
and executes a sequence of commands from 'listener_config.yaml' for both devices.

Requires PyYAML: pip install PyYAML
"""

import time
import sys
import yaml # Requires PyYAML
import argparse
import os

# --- Import SQ Controller Code ---
import sq_midi_controller as sq
from sq_midi_controller import (
    SocketConnection as SQSOCKET,
    SQMidiProtocol
)

# --- Import Kramer Controller Code ---
from proto3k import (
    KramerSocketConnection,
    KramerProtocol,
    Route as KramerRoute,
    VideoMute as KramerVideoMute
)

# --- Import MIDI Note Definitions ---
from midi_notes import NOTE_LOOKUP

# --- Configuration is now loaded from YAML ---
# Removed: SQ_MIXER_IP, KRAMER_IP, PRESET_FILE, MIDI_CHANNEL, PRESETS
DEFAULT_CONFIG_FILE = "listener_config.yaml"


def load_configuration() -> (dict, dict):
    """
    Loads configuration and presets from a YAML file.
    The file path is determined by:
    1. Command-line argument (-c or --config)
    2. Environment variable (MIDI_PRESET_FILE)
    3. Default value (DEFAULT_CONFIG_FILE)
    """
    parser = argparse.ArgumentParser(description="SQ/Kramer MIDI Listener")
    parser.add_argument(
        '-c', '--config',
        metavar='CONFIG_FILE',
        type=str,
        default=os.environ.get('MIDI_PRESET_FILE', DEFAULT_CONFIG_FILE),
        help=f"Path to the config/preset YAML file. "
             f"(Env: MIDI_PRESET_FILE, Default: {DEFAULT_CONFIG_FILE})"
    )
    args = parser.parse_args()
    config_file_path = args.config

    print(f"Loading configuration from {config_file_path}...")
    try:
        with open(config_file_path, 'r') as f:
            data = yaml.safe_load(f)
            if not data:
                print(f"FATAL ERROR: Config file '{config_file_path}' is empty.")
                sys.exit(1)
            
            app_config = data.get('config', {})
            presets = data.get('presets', {})
            
            if not app_config:
                print(f"FATAL ERROR: 'config' section not found in {config_file_path}.")
                sys.exit(1)
            if not presets:
                print(f"Warning: 'presets' section not found or empty in {config_file_path}.")

            print(f"Successfully loaded {len(presets)} presets: {list(presets.keys())}")
            return app_config, presets
            
    except FileNotFoundError:
        print(f"FATAL ERROR: Config file '{config_file_path}' not found.", file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"FATAL ERROR: Could not parse '{config_file_path}': {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"FATAL ERROR: An unexpected error occurred loading config: {e}", file=sys.stderr)
        sys.exit(1)


def execute_preset(preset_name: str, actions: dict, sq_ctrl: SQMidiProtocol, kramer_ctrl: KramerProtocol):
    """
    Executes all commands defined in a preset for all devices.
    """
    print(f"--- EXECUTING PRESET: {preset_name} ---")
    
    # --- Execute SQ Commands ---
    if "SQ" in actions and sq_ctrl:
        sq_actions = actions["SQ"]
        for action in sq_actions:
            try:
                command, args = list(action.items())[0]
                
                if command == "RecallScene":
                    sq_ctrl.send_message(sq.RecallScene(scene_number=int(args)))
                
                elif command == "SetMute":
                    # args: [from, to, bool]
                    sq_ctrl.send_message(sq.SetMuteNRPN(args[0], args[1], mute_on=bool(args[2])))
                
                elif command == "SetFaderLevel":
                    # args: [from, to, level_db]
                    level_db = float(args[2])
                    level_14bit = sq.db_to_fader_level(level_db)
                    sq_ctrl.send_message(sq.SetFaderLevelNRPN(args[0], args[1], level=level_14bit))
                
                elif command == "SetPan":
                    # args: [from, to, pan_float]
                    pan_float = float(args[2])
                    pan_14bit = sq.pan_to_value(pan_float)
                    sq_ctrl.send_message(sq.SetPanNRPN(args[0], args[1], pan_value=pan_14bit))
                
                elif command == "SetAssign":
                    # args: [from, to, bool]
                    sq_ctrl.send_message(sq.SetAssignNRPN(args[0], args[1], assign_on=bool(args[2])))
                
                elif command == "Wait":
                    print(f"  [Wait] Pausing for {args} seconds...")
                    time.sleep(float(args))
                
                else:
                    print(f"Warning: Unknown SQ command '{command}' in preset.")
                    
            except Exception as e:
                print(f"Error executing SQ command {action}: {e}", file=sys.stderr)

    # --- Execute Kramer Commands ---
    if "Kramer" in actions and kramer_ctrl:
        kramer_actions = actions["Kramer"]
        for action in kramer_actions:
            try:
                command, args = list(action.items())[0]
                
                if command == "Route":
                    # Support for optional dest/layer from YAML in the future
                    # For now, assumes args is just the source
                    kramer_ctrl.send_message(KramerRoute(source=int(args)))
                
                elif command == "VideoMute":
                    # Support for optional dest/layer from YAML in the future
                    # For now, assumes args is just the enable/disable/blank flags
                    kramer_ctrl.send_message(KramerVideoMute(flag=int(args)))
                
                else:
                    print(f"Warning: Unknown Kramer command '{command}' in preset.")
                    
            except Exception as e:
                print(f"Error executing Kramer command {action}: {e}", file=sys.stderr)

    print(f"--- PRESET {preset_name} COMPLETE ---")


def parse_midi_message(data: bytes, sq_ctrl: SQMidiProtocol, kramer_ctrl: KramerProtocol, midi_channel: int, presets: dict):
    """
    Parses a raw byte buffer for MIDI Note On messages and triggers presets.
    """
    i = 0
    while i < len(data):
        if data[i] & 0x80: # Is the 8th bit set? (Status Byte)
            
            # Check for Note On (0x9n) on our target channel
            status_byte_base = 0x90 + (midi_channel - 1)
            
            if data[i] == status_byte_base and i + 2 < len(data):
                note = data[i+1]
                velocity = data[i+2]
                
                if velocity > 0: # Note On (not Note Off)
                    print(f"\n[MIDI IN] Note On Received: Note={note} (0x{note:X}), Velocity={velocity}")
                    
                    # --- Find and Trigger Preset ---
                    note_name = NOTE_LOOKUP.get(note)
                    if note_name and note_name in presets:
                        actions = presets[note_name]
                        execute_preset(note_name, actions, sq_ctrl, kramer_ctrl)
                    elif note in presets:
                        actions = presets[note]
                        execute_preset(note_name, actions, sq_ctrl, kramer_ctrl)
                    else:
                        print(f"[MIDI IN] Note {note} ('{note_name}') has no preset assigned.")
                    
                i += 3 # Move past this 3-byte message
            else:
                # Other message, skip it
                i += 1
        else:
            i += 1


def main():
    """
    Main connection and listening loop.
    """
    app_config, presets = load_configuration()
    
    # --- Extract Config Values ---
    listener_config = app_config.get('midi_listener', {})
    sq_config = app_config.get('SQ', {})
    kramer_config = app_config.get('Kramer', {})

    midi_channel = listener_config.get('channel', 1)
    sq_ip = sq_config.get('ip')
    sq_port = sq_config.get('port', 51325) # Default if not in YAML
    kramer_ip = kramer_config.get('ip')
    kramer_port = kramer_config.get('port', 5000) # Default if not in YAML

    if not sq_ip:
        print("FATAL ERROR: 'config.SQ.ip' not set in config file.", file=sys.stderr)
        sys.exit(1)
    if not kramer_ip:
        print("FATAL ERROR: 'config.Kramer.ip' not set in config file.", file=sys.stderr)
        sys.exit(1)

    print("--- Allen & Heath SQ / Kramer MIDI Listener ---")
    
    while True: # Loop forever to reconnect if connection drops
        sq_controller = None
        kramer_controller = None
        try:
            # We nest the connections.
            # First, connect to the SQ (the MIDI source)
            with SQSOCKET(sq_ip, sq_port) as sq_controller:
                print(f"\nSuccessfully connected to SQ Mixer at {sq_ip}:{sq_port}.")
                
                # Now, try to connect to the Kramer
                try:
                    with KramerSocketConnection(kramer_ip, kramer_port) as kramer_controller:
                        print(f"\nSuccessfully connected to Kramer at {kramer_ip}:{kramer_port}.")
                        print("--- All systems connected. Listening for MIDI... (Press CTRL-C to exit) ---")
                        
                        while True: # Main listening loop
                            data = sq_controller.listen_blocking()
                            if data:
                                parse_midi_message(data, sq_controller, kramer_controller, midi_channel, presets)
                                
                except ConnectionRefusedError:
                    print(f"\n--- KRAMER CONNECTION FAILED ---")
                    print(f"Could not connect to {kramer_ip}:{kramer_port}.")
                    print("Running in SQ-ONLY mode. Kramer commands will be skipped.")
                    print("--- Listening for MIDI... (Press CTRL-C to exit) ---")
                    
                    while True: # Listen loop (SQ only)
                        data = sq_controller.listen_blocking()
                        if data:
                            parse_midi_message(data, sq_controller, None, midi_channel, presets) # Pass None for Kramer

        except ConnectionRefusedError:
            print(f"\n--- SQ MIXER CONNECTION FAILED ---")
            print(f"Could not connect to {sq_ip}:{sq_port}.")
            print("Retrying in 5 seconds...")
            
        except KeyboardInterrupt:
            print("\nShutdown signal (CTRL-C) received. Exiting.")
            sys.exit(0)
            
        except Exception as e:
            print(f"A critical error occurred: {e}. Restarting in 5 seconds...", file=sys.stderr)
            
        time.sleep(5)


if __name__ == "__main__":
    main()