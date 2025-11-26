# Bucks Church Scripts

This repository contains a collection of Python scripts and configuration files designed to automate and control audio/video (AV) equipment at Bucks County Community Church (BCCC). The scripts primarily manage devices such as the Allen & Heath SQ audio mixer, Kramer video switchers (using Protocol 3000), PTZ Optics cameras (via VISCA protocol), Kasa smart plugs for TVs, and Blackmagic ATEM video switchers. These tools are used for tasks like switching video sources, controlling audio mixes, turning devices on/off, and responding to MIDI triggers from the SQ mixer.

The core functionality revolves around a MIDI listener that integrates the SQ mixer with the Kramer switcher, allowing SoftKey triggers on the mixer to execute predefined AV presets. Additional standalone scripts handle specific device controls.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Scripts Overview](#scripts-overview)
  - [Core MIDI Listener System](#core-midi-listener-system)
  - [Kramer Video Switcher Controls](#kramer-video-switcher-controls)
  - [TV Controls (Kasa Smart Plugs)](#tv-controls-kasa-smart-plugs)
  - [Camera Controls (PTZ Optics)](#camera-controls-ptz-optics)
  - [ATEM Video Switcher](#atem-video-switcher)
  - [Audio Distribution](#audio-distribution)
- [Usage Examples](#usage-examples)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Prerequisites

- **Python 3.9+**: Most scripts are written in Python. Ensure you have Python installed.
- **Libraries**:
  - `PyYAML`: For loading configuration files (install via `pip install PyYAML`).
  - `PyATEMMax`: For ATEM switcher control (install via `pip install PyATEMMax`).
  - `kasa`: For Kasa smart plug control (install via `pip install kasa`).
  - No additional installs needed for core socket-based scripts (e.g., MIDI, Protocol 3000, VISCA).
- **Hardware/Network Setup**:
  - Allen & Heath SQ Mixer (e.g., at IP `192.168.7.158:51325`).
  - Kramer Video Switcher (e.g., SWT3-41-H at IP `192.168.7.100:5000` or `192.168.1.208:5000`).
  - PTZ Optics Cameras (e.g., at IPs `192.168.1.60-62:5678`).
  - Kasa Smart Strips/Plugs controlling TVs (discoverable on the network).
  - Blackmagic ATEM Switcher (e.g., at IP `192.168.1.35`).
  - Network access to all devices (update IPs in scripts/config as needed).
- **Operating System**: Scripts are cross-platform but tested on Windows (e.g., `.bat` and `.ps1` files). For macOS/Linux, adapt as needed.
- **Documentation**: The repository includes `protocol_3000_3.0_master_user.pdf` for Kramer Protocol 3000 reference.

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/BucksCountyCommunityChurch/buckschurch_scripts.git
   cd buckschurch_scripts
   ```

2. Install Python dependencies:
   ```
   pip install PyYAML PyATEMMax kasa
   ```

3. Customize IPs and ports in scripts or config files (see [Configuration](#configuration)).

## Configuration

Most configuration is handled via `listener_config.yaml`, which defines MIDI listener settings and presets for the SQ mixer and Kramer switcher.

- **Structure**:
  ```yaml
  config:
    midi_listener:
      channel: 1  # MIDI channel to listen on (1-16)
    SQ:
      ip: "192.168.7.158"  # SQ Mixer IP
      port: 51325  # SQ MIDI port
    Kramer:
      ip: "192.168.7.100"  # Kramer IP
      port: 5000  # Kramer Protocol 3000 port

  presets:
    "C3":  # MIDI note (from midi_notes.py)
      "SQ":  # Commands for SQ Mixer
        - "RecallScene": 1
        - "Wait": 2.5
        - "SetMute": [ "IP1", "LR", false ]  # [from_ch, to_ch, true/false]
        # ... more SQ commands
      "Kramer":  # Commands for Kramer
        - "Route": 1  # Switch to video source 1
    "D3":
      # ... additional presets
  ```

- **SQ Commands**:
  - `RecallScene`: Recall a scene by number.
  - `SetMute`: Mute/unmute a channel crosspoint.
  - `SetFaderLevel`: Set fader level in dB.
  - `SetPan`: Set pan (-100 to +100).
  - `SetAssign`: Assign/unassign a channel.
  - `Wait`: Delay in seconds.

- **Kramer Commands**:
  - `Route`: Switch video source (1-4 in examples).

- **Environment Variables**:
  - `MIDI_PRESET_FILE`: Override the config file path (default: `listener_config.yaml`).

Update IPs, ports, and presets to match your setup. MIDI notes are defined in `midi_notes.py` (e.g., "C3" = 48).

## Scripts Overview

### Core MIDI Listener System

These scripts form the backbone for MIDI-triggered automation between the SQ mixer and Kramer switcher.

- **`midi_listener.py`**:
  - Listens for MIDI Note On messages from the SQ mixer (triggered by SoftKeys).
  - Executes preset commands from `listener_config.yaml` for SQ and Kramer.
  - Handles reconnections if devices drop.
  - Usage: `python midi_listener.py` (or with `--config path/to/config.yaml`).

- **`sq_midi_controller.py`**:
  - Core logic for sending MIDI NRPN commands to the SQ mixer (e.g., mute, fader, pan).
  - Includes helper functions like `db_to_fader_level` and `pan_to_value`.
  - Uses `sq_midi_db.py` for NRPN address mappings.

- **`sq_midi_db.py`**:
  - Database of NRPN addresses for SQ controls (e.g., Mute, Fader, Pan, Assign).
  - Builds a channel address map from base offsets.

- **`proto3k.py`**:
  - Implements Kramer Protocol 3000 for socket communication.
  - Supports commands like `Route` for video source switching.
  - Includes context manager for connections.

- **`midi_notes.py`**:
  - Defines MIDI note constants (e.g., C3=48) for SoftKey triggers.

### Kramer Video Switcher Controls

Standalone scripts to switch video sources on the Kramer SWT3-41-H using Protocol 3000.

- **`switch_source1.py`**, **`switch_source2.py`**, **`switch_source3.py`**, **`switch_source4.py`**:
  - Switch to source 1-4 respectively.
  - Hardcoded IP: `192.168.1.208:5000` (update as needed).
  - Usage: `python switch_source1.py`.

### TV Controls (Kasa Smart Plugs)

Scripts to control TVs via Kasa smart strips/plugs.

- **`kasatv.py`**:
  - Discovers Kasa devices and sends ON/OFF commands to specific TVs (e.g., "FoyerTV").
  - Usage: Import and call functions like `send_to_tvs(devices, Commands.ON)`.

- **`tvs_on.py`**, **`tvs_off.py`**:
  - Turn all discovered TVs on/off.
  - Usage: `python tvs_on.py`.

### Camera Controls (PTZ Optics)

Scripts for basic power control of PTZ Optics cameras using VISCA protocol.

- **`viscacam.py`**:
  - Sends VISCA commands (ON/OFF) to cameras at hardcoded IPs (`192.168.1.60-62:5678`).
  - Usage: Import and call `send_command(viscacam.CAM_ON)`.

- **`cams_on.py`**, **`cams_off.py`**:
  - Turn all cameras on/off.
  - Usage: `python cams_on.py`.

### ATEM Video Switcher

- **`atem_switch.py`**:
  - Executes an auto-transition on the ATEM switcher (Mix Effect 0).
  - Hardcoded IP: `192.168.1.35` (update in script).
  - Usage: `python atem_switch.py`.

- **`run_atem_autoswitch.bat`**:
  - Windows batch file to run `atem_switch.py`.
  - Usage: Double-click or run from command line.

### Audio Distribution

- **`set_audio_distribution.ps1`**:
  - PowerShell script to set the default audio output device to "SYLVANIA" (building video distribution).
  - Requires `Set-AudioDevice` cmdlet (install via PowerShell modules if needed).
  - Usage: Run in PowerShell: `.\set_audio_distribution.ps1`.

## Usage Examples

1. **Run MIDI Listener**:
   ```
   python midi_listener.py
   ```
   - Triggers presets on MIDI notes (e.g., C3 recalls SQ scene 1 and routes Kramer to source 1).

2. **Switch Kramer Source**:
   ```
   python switch_source2.py
   ```

3. **Turn TVs On**:
   ```
   python tvs_on.py
   ```

4. **Turn Cameras Off**:
   ```
   python cams_off.py
   ```

5. **ATEM Auto Switch**:
   ```
   run_atem_autoswitch.bat
   ```

## Troubleshooting

- **Connection Issues**: Verify IPs/ports in configs/scripts. Check firewalls and device power.
- **MIDI Not Triggering**: Ensure SQ SoftKeys are set to send MIDI notes on the configured channel.
- **Dependencies**: If `kasa` discovery fails, ensure devices are on the same network.
- **Errors**: Scripts log to console; check for timeouts or parsing issues.
- **Kramer Protocol**: Refer to `protocol_3000_3.0_master_user.pdf` for advanced commands.

## Contributing

Contributions are welcome! Fork the repo, make changes, and submit a pull request. Focus on adding more presets, device support, or error handling.

## License

This repository is licensed under the MIT License. See [LICENSE](LICENSE) for details (if not present, assume open-source for church use).
