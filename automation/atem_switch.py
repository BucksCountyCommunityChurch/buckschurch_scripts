# coding: utf-8
"""change-settings.py - PyATEMMax demo script.
   Part of the PyATEMMax library."""


import sys
import time
import PyATEMMax

class Args (object):
	ip = "192.168.1.35"
	mixeffect = 0
	
args = Args()

switcher = PyATEMMax.ATEMMax()
count = 0

print(f"[{time.ctime()}] Starting settings update")
print(f"[{time.ctime()}] Connecting to {args.ip}")

switcher.connect(args.ip)
if switcher.waitForConnection(infinite=False):

    print(f"[{time.ctime()}] Executing Auto switch on {switcher.atemModel} with MixEffect {args.mixeffect}")
    switcher.execAutoME(args.mixeffect)
    print(f"[{time.ctime()}] Settings updated on {switcher.atemModel} at {args.ip}")

else:
    print(f"[{time.ctime()}] ERROR: no response from {args.ip}")
switcher.disconnect()