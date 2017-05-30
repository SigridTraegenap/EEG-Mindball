#
#  TESTING (This program allows to read the Serial data stream from the Arduino.)
#

import serial
import numpy as np
import matplotlib.pyplot as plt
import time


BUFFER_SIZE = 100

def serial_com():
	'''Serial communications: get a response'''
	# open serial port
	try:
		serial_port = serial.Serial('/dev/ttyACM0', baudrate=115200, bytesize=8)#, timeout=None, xonxoff=True)#115200,230400
		#serial_port.open()
		serial_port.readline()
		serial_port.write('conf s:10000;c:1;\n')
		time.sleep(0.5)
	except serial.SerialException as e:
		print("could not open serial port '{}': {}".format('/dev/ttyACM0', e))
	
	data = []
	time0 = time.time()
	while (time.time() - time0 < 10):  # Read data for 10 seconds
		#bytesToRead = serial_port.inWaiting()
		data.append(serial_port.read(BUFFER_SIZE))
	serial_port.close()
	print('data',len(data))

	
	
	lines = []
	ist = 0
	for line in data:
		if line.find('StartUp')>0:
			line = line[line.find('StartUp',beg=0)+10:]
		lines.append(np.fromstring(line,dtype=np.uint8))
	lines = np.array(lines).flatten()
	
	foundBeginingOfFrame = 0
	result = []
	for i in np.arange(0,len(lines)-1,2):
		if foundBeginingOfFrame==0:
			if(lines[i]>127):
				#print('foundBeginingOfFrame')
				foundBeginingOfFrame = 1
				##extract one sample from 2 bytes
				intout = np.uint16(np.uint16(lines[i] & 127)*128)
				intout = intout + np.uint16(lines[i+1])
				result.append(intout)
		else:
			##extract one sample from 2 bytes
			intout = np.uint16(np.uint16(lines[i] & 127)*128);
			intout = intout + np.uint16(lines[i+1]);
			result.append(intout)
	return result

# get the last 10s from serial port
lines = serial_com()
#print(lines)
print('done')

# plot the output from serial port
fig = plt.figure()
ax = fig.add_subplot(111)
ax.plot(lines)
plt.show()
