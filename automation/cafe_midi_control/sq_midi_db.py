"""
This file acts as a database, storing the address mappings
from the 'SQ-MIDI-Generator.xlsx - Reference.csv' file.

This is kept separate to make it easier to add more
channels and controls as you need them.
"""

# These are the "Base Addresses" for each control type,
# taken from the 'Generator.csv' and 'Reference.csv' files.
CONTROL_BASE_ADDRESS = {
    "Mute": 0x0000,    # (MSB 0x00 << 7)
    "Fader": 8192,    # (MSB 0x40 << 7) = 0x2000
    "Pan": 10240,     # (MSB 0x50 << 7) = 0x2800
    "Assign": 12288,  # (MSB 0x60 << 7) = 0x3000
}

# These are the base "Address" offsets for each "To" destination,
# taken from column F of 'Reference.csv' (e.g., Address for "IP1 -> LR" is 0)
TO_CHANNEL_BASE_ADDRESS = {
    "LR": 0, "AUX1": 128, "AUX2": 256, "AUX3": 384, 
    "AUX4": 512, "AUX5": 640, "AUX6": 768, "AUX7": 896, 
    "AUX8": 1024, "AUX9": 1152, "AUX10": 1280, "AUX11": 1408, 
    "AUX12": 1536, "GRP1": 1664, "GRP2": 1792, "GRP3": 1920, 
    "GRP4": 2048, "GRP5": 2176, "GRP6": 2304, "GRP7": 2432, 
    "GRP8": 2560, "GRP9": 2688, "GRP10": 2816, "GRP11": 2944, 
    "GRP12": 3072, "FXSND1": 3200, "FXSND2": 3328, "FXSND3": 3456, 
    "FXSND4": 3584, "MTX1": 3712, "MTX2": 3840, "MTX3": 3968, 
    "MTX4": 4096, "MTX5": 4224, "MTX6": 4352, "MTX7": 4480, 
    "MTX8": 4608, "MTX9": 4736, "MTX10": 4864, "MTX11": 4992, 
    "MTX12": 5120,
}

# A utility map used by the _build_channel_address_map function
_BUS_CHANNELS = list(TO_CHANNEL_BASE_ADDRESS.keys())


def _build_channel_address_map() -> dict:
    """
    Builds the complete mapping of (From_Channel, To_Channel) pairs
    to their specific 14-bit NRPN address offset (0-5120).
    """
    print("Building SQ MIDI Address Map...")
    address_map = {}
    
    # Iterate over all "To" destinations
    for to_ch, base_addr in TO_CHANNEL_BASE_ADDRESS.items():
        
        # 1. Add Input Channels (IP1 to IP48)
        for i in range(1, 49):
            from_ch = f"IP{i}"
            pair = (from_ch, to_ch)
            address_map[pair] = base_addr + (i - 1)
            
        # 2. Add FX Returns (FXRTN1 to FXRTN8)
        # FXRTNs start at offset 48 for each bus
        for i in range(1, 9):
            from_ch = f"FXRTN{i}"
            pair = (from_ch, to_ch)
            # e.g., FXRTN1 adds 48, FXRTN2 adds 49, etc.
            address_map[pair] = base_addr + (i - 1) + 48

    # --- Add Master Bus Controls (e.g., LR Master Mute) ---
    # These are separate masters, not crosspoints.
    print("Adding Master Bus controls...")
    
    # LR Master (Address 2424)
    address_map[("LR", "LR")] = 2424
    
    # AUX1-12 Masters (Address 2504 to 2515)
    for i in range(1, 13):
        ch_name = f"AUX{i}"
        address_map[(ch_name, ch_name)] = 2503 + i
        
    # GRP1-12 Masters (Address 2516 to 2527)
    for i in range(1, 13):
        ch_name = f"GRP{i}"
        address_map[(ch_name, ch_name)] = 2515 + i
        
    # FXSND1-4 Masters (Address 2528 to 2531)
    for i in range(1, 5):
        ch_name = f"FXSND{i}"
        address_map[(ch_name, ch_name)] = 2527 + i
        
    # FXRTN1-8 Masters (Address 2532 to 2539)
    for i in range(1, 9):
        ch_name = f"FXRTN{i}"
        address_map[(ch_name, ch_name)] = 2531 + i
        
    # MTX1-12 Masters (Address 2540 to 2551)
    for i in range(1, 13):
        ch_name = f"MTX{i}"
        address_map[(ch_name, ch_name)] = 2539 + i

    print(f"Address Map built with {len(address_map)} entries.")
    return address_map

# This map translates (From, To) pairs into the
# specific 14-bit NRPN address offset (e.g., ("IP1", "LR") -> 0)
CHANNEL_ADDRESS_MAP = _build_channel_address_map()


def get_nrpn_address(control: str, from_ch: str, to_ch: str) -> int:
    """
    Looks up the full NRPN address (Base + Channel Offset) for a given control.
    """
    if control not in CONTROL_BASE_ADDRESS:
        raise KeyError(f"Control type '{control}' not found in CONTROL_BASE_ADDRESS. Available: {list(CONTROL_BASE_ADDRESS.keys())}")
        
    pair = (from_ch, to_ch)
    if pair not in CHANNEL_ADDRESS_MAP:
        raise KeyError(f"Channel pair {pair} not found in CHANNEL_ADDRESS_MAP. Check channel spelling (e.g., 'IP1', 'LR', 'AUX1').")

    base_addr = CONTROL_BASE_ADDRESS[control]
    channel_addr = CHANNEL_ADDRESS_MAP[pair]

    # The final address is the base + channel offset
    final_address = base_addr + channel_addr

    # Validate that the final address fits in 14 bits (0-16383)
    if not (0 <= final_address <= 16383):
        raise ValueError(f"Calculated address {final_address} is outside the 14-bit NRPN range (0-16383).")

    return final_address