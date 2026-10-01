# Manual test of the DTR reset line: opens the serial port and toggles DTR. Edit `port` and
# `baudrate` below first; needs pyserial. Not run by the test suites.
import serial
import time

#port              = "/dev/tty.usbserial-1420"
#port              = "/dev/cu.usbserial-0001"
port              = "/dev/cu.SLAB_USBtoUART"
#port              = "/dev/cu.usbserial-1420"

#baudrate         = 9600
baudrate          = 19200
#baudrate         = 38400
#baudrate         = 57600
#baudrate         = 115200

stopbits          = 1

if (stopbits == 1):
  stopbits_constant = serial.STOPBITS_ONE
elif (stopbits == 2):
  stopbits_constant = serial.STOPBITS_TWO
else:
  raise ValueError("Stop bits must be 1 or 2") 

print("Starting dtr test.")

with serial.Serial(
  port=None,
  baudrate=baudrate,
  stopbits=stopbits_constant) as ser:
  time.sleep(2.0)

  ser.port=port
  ser.dtr = False
  ser.open()
  print ("Opened with dtr = False")

  while (True):
    time.sleep(2.0)
    ser.dtr = True
    print ("Dtr set to True")
    time.sleep(2.0)
    ser.dtr = False
    print ("Dtr set to False")
