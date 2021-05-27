import asyncio
import time
from enum import Enum
from kasa import SmartStrip
from kasa import Discover

TVs = ["BCCC KP303 1-1", "FellowshipCafeTV", "BreezewayTV", "FoyerTV"]


class Commands(Enum):
    ON = 1
    OFF = 2

COMMANDS_TO_STRING = {
    Commands.ON: "on",
    Commands.OFF: "off",
    }

async def send_cmd(device, child_name, cmd):

    await device.update()
    #print (device.alias)

    obj = device
    if child_name is not None:
        obj = [child for child in device.children if child.alias == child_name]
        if len(obj):
            obj = obj[0]

    if cmd == Commands.ON:
        await obj.turn_on()
        await device.update()
        print (f"{obj.alias} is { ('on' if obj.is_on else 'off')}")

    elif cmd == Commands.OFF:
        await obj.turn_off()
        await device.update()
        print (f"{obj.alias} is { ('on' if obj.is_on else 'off')}")


def discover_strips():
    async def print_device(found_device):
        await found_device.update()
        print (f"Found: {found_device.alias}")
    devices = asyncio.run(Discover.discover(on_discovered=print_device))
    #print(devices)
    return devices

def send_to_tvs(devices, cmd):
    for d in devices.values():
        tv = "".join([ c.alias for c in d.children if c.alias in TVs])
        if tv:
            print(f"Turning {COMMANDS_TO_STRING[cmd]} {tv}")
            asyncio.run(send_cmd(d, tv, cmd))
            time.sleep(2)

if __name__ == "__main__":
    devices = discover_strips()
    print (devices)

    