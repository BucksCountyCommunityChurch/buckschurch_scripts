import kasatv


''' Turn on the BCCC TVs '''
devices = kasatv.discover_strips()
kasatv.send_to_tvs(devices, kasatv.Commands.ON)
