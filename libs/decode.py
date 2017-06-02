import numpy as np

def decode_output(line):
	line = np.fromstring(line,dtype=np.uint8)
	foundBeginingOfFrame = 0
	result = []
	for i in np.arange(0,len(line)-1,2):
		if foundBeginingOfFrame==0:
			if(line[i]>127):
				#print('foundBeginingOfFrame')
				foundBeginingOfFrame = 1
				##extract one sample from 2 bytes
				intout = np.uint16(np.uint16(line[i] & 127)*128)
				intout = intout + np.uint16(line[i+1])
				result.append(intout)
		else:
			##extract one sample from 2 bytes
			intout = np.uint16(np.uint16(line[i] & 127)*128);
			intout = intout + np.uint16(line[i+1]);
			result.append(intout)
	return result
