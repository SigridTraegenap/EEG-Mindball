import numpy as np

def decode_output(line):
	line = np.fromstring(line,dtype=np.uint8)
	foundBeginingOfFrame = 0
	delta = 1
	result = []
	i = 0
	#print(len(line))
	while i<(len(line)-1):
		#print(i)
		if foundBeginingOfFrame==0:
			if(line[i]>127):
				#print('foundBeginingOfFrame')
				foundBeginingOfFrame = 1
				##extract one sample from 2 bytes
				intout = np.uint16(np.uint16(line[i] & 127)*128)
				intout = intout + np.uint16(line[i+1])
				result.append(intout)
				i += 2
			else:
				i += 1
		else:
			##extract one sample from 2 bytes
			intout = np.uint16(np.uint16(line[i] & 127)*128);
			intout = intout + np.uint16(line[i+1]);
			result.append(intout)
			i += 2
	return result
			
	
