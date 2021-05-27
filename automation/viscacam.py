import socket
import time

CAM1 = "192.168.1.60"
CAM2 = "192.168.1.61"
CAM3 = "192.168.1.62"

CAM_PORT = 5678

CAM_ON  = bytearray.fromhex('8101040002ff')
CAM_OFF  = bytearray.fromhex('8101040003ff')

command=CAM_ON

def send_command(command):

    for cam_host in [ CAM1, CAM2, CAM3 ]:
        port = CAM_PORT
        print("Connecting to ",cam_host)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(0.5)
            s.connect((cam_host, CAM_PORT))
            print("Connected")
            s.sendall(command)
            data = s.recv(1024)
            print("Command Sent")
            s.close()
            print("Connection Closed")
        except Exception as ex:
            print("Error Sending command ", repr(ex))
        time.sleep(2)


if __name__ == "__main__":
    send_command(CAM_ON)

