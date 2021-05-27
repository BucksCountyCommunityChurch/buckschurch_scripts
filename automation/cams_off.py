import viscacam


''' Turn off the PTZ Optics Cameras '''
devices = viscacam.send_command(viscacam.CAM_OFF)
