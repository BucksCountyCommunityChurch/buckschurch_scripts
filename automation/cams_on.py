import viscacam


''' Turn on the PTZ Optics Cameras '''
devices = viscacam.send_command(viscacam.CAM_ON)
