""" 
A simple demonstration of a serial port monitor that plots live
data using pyqtgraph.
The monitor expects to receive 8-byte data packets on the 
serial port. The packages are decoded such that the first byte
contains the 3 most significant bits and the second byte contains
the 7 least significat bits.
"""
import numpy as np
import random, sys
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import pyqtgraph as pg
import Queue

from com_monitor import ComMonitorThread
from libs.utils import get_all_from_queue, get_item_from_queue
from libs.decode import decode_output
from livedatafeed import LiveDataFeed
from libs.read_audio import play_sound

from scipy.interpolate import interp1d
from scipy.signal import butter, lfilter


## plotting parameters
color1 = "#FF7D00"   #orange
color2 = "#4814CC"  #blue
name_color1 = "orange"
name_color2 = "blue"
width_signal = 5
time_axis_range = 2 ## in s

#fixes to white background and black labels
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

sound_path = '/home/bettina/physics/arduino/eeg_mindball/sound/'
sound_files = ['End_of_football_game','Football-crowd-GOAL','intro_brass_01','Jingle_Win_00','Jingle_Win_01']

class PlottingDataMonitor(QMainWindow):
	def __init__(self, parent=None):
		super(PlottingDataMonitor, self).__init__(parent)
		
		self.monitor_active = False
		self.com_monitor = None
		self.com_monitor2 = None
		self.livefeed = LiveDataFeed()
		self.livefeed2 = LiveDataFeed()
		self.temperature_samples = []
		self.temperature_samples2 = []
		self.timer = QTimer()
		
		self.create_menu()
		
		self.yaxis_low,self.yaxis_high = 300,600
		self.create_main_frame()
		self.create_status_bar()
		
		## spectrum boundaries
		self.x_low = 4
		self.x_high = 13
		self.frequency = 1 ##Hz
		self.nmax = 1000
		self.fft1_norm = np.zeros((self.nmax//2))
		self.b, self.a = butter(3, [0.0, 0.34], btype='band')
		
		
		## init arena stuff
		self.ball_coordx = 0.
		self.ball_coordy = 0.
		self.tuning_factor = 5.
		self.text_html = '<div style="text-align: center"><span style="color: #FFF; font-size: 40pt">Goal</span><br><span style="color: #FFF; font-size: 40pt; text-align: center"> {} is winner </span></div>'
		self.show_one_item = False
		self.winner_text = None
		self.playing = False
		self.win_hymn_no = 2
	
	def create_plot(self, xlabel, ylabel, xlim, ylim, ncurves=1):
		plot = pg.PlotWidget()
		curve = plot.plot(antialias=True)
		plot.setLabel('left', ylabel)
		plot.setLabel('bottom', xlabel)
		plot.setXRange(xlim[0], xlim[1])
		plot.setYRange(ylim[0], ylim[1])

		#plot.setCanvasBackground(Qt.black)
		plot.replot()
		
		pen = QPen(QColor(color1))
		#pen.setWidth(1.5)
		#setting this width increases also fft width - do not use 
		curve.setPen(pen)
		
		if ncurves==2:
			curve2 = plot.plot(antialias=True)
			#pen.setWidth(0.9)
			pen2 = QPen(QColor(color2))
			curve2.setPen(pen2)
			return plot, curve, curve2
		else:
			return plot, curve

	def create_arenaplot(self, xlabel, ylabel="Player "+color1, xlim=[-1,1], ylim=[-1,1], curve_style=None):
		""" create plot/arena in form of a soccer field
		"""
		plot = pg.PlotWidget(background=QColor("#008A0E"))
		if curve_style is not None:
			curve = plot.plot(symbol=curve_style,antialias=True, symbolSize=15, symbolBrush='w')
		else:
			curve = plot.plot(antialias=True)
		plot.setLabel('left', ylabel)
		plot.setLabel('bottom', xlabel)
		plot.setXRange(xlim[0], xlim[1], 0.1)
		plot.setYRange(ylim[0], ylim[1], 0.1)
		plot.hideAxis('bottom')
		plot.hideAxis('left')
		plot.replot()
		
		spi = pg.ScatterPlotItem(size=5, pen=pg.mkPen(None), brush=pg.mkBrush(255,255,255,255))
		spi.addPoints([{'pos' : [0,0], 'data' : 1}])
		plot.addItem(spi)
		
		spi = pg.ScatterPlotItem(size=70, brush=pg.mkBrush(255,255,255,0))
		spi.addPoints([{'pos' : [0,0], 'data' : 1, 'pen' : 'w'}])
		plot.addItem(spi)
		
		central_line = pg.GraphItem()
		plot.addItem(central_line)
		w = 0.5
		pos = np.array([[0.,-1.],[0.,1.],[-1.,w],[-0.7,w],[-0.7,-w],
		[-1.,-w],[1,w],[0.7,w],[0.7,-w],[1,-w], [-1,-1],[-1,1], [1,-1],[1,1],
		[-1,0.2],[-1.1,0.2],[-1.1,-0.2],[-1,-0.2],
		[1,0.2],[1.1,0.2],[1.1,-0.2],[1,-0.2]])

		adj = np.array([[0,1], [2,3],[3,4],[4,5], [6,7],[7,8],[8,9],[10,12],[11,13],
		[14,15],[15,16],[16,17],[18,19],[19,20],[20,21], [10,11],[12,13]])

		#color1, color2 (magenta, green)
		lines = np.array([(255,255,255,255,1)]*15 + [(72,20,204,255,4),(255,125,0,255,4)],
		dtype=[('red',np.ubyte),('green',np.ubyte),('blue',np.ubyte),('alpha',np.ubyte),('width',float)])
		central_line.setData(pos=pos,adj=adj,pen=lines,size=0.1)

		return plot, curve

	def create_status_bar(self):
		self.status_text = QLabel('Monitor idle')
		self.statusBar().addWidget(self.status_text, 1)

	
	def SliderValueChanged_fft(self):
		ymax = self.slider_fft_y.sliderPosition()/1000.
		self.plot_fft.setYRange(0,ymax)
	
	def SliderValueChanged(self):
		ymax = self.slider_signal_y.sliderPosition()
		self.plot.setYRange(300,ymax)
	
	def create_main_frame(self):
		# Main frame and layout
		#
		self.mdi = QMdiArea()
		self.setWindowTitle("FIAS - EEG Mind Ball")
		#self.main_frame = QWidget()
		#main_layout = QGridLayout()
		#main_layout.setColumnStretch(0,1)


		## Plotting
		## buttons
		self.button_start = QPushButton('Start', self)
		self.button_start.clicked.connect(self.on_start)
		
		self.button_stop = QPushButton('Stop', self)
		self.button_stop.clicked.connect(self.on_stop)
		
		## sliders
		self.slider_signal_y = QSlider(Qt.Vertical)
		self.slider_signal_y.setRange(300,1000)
		self.slider_signal_y.setValue(self.yaxis_high)
		self.slider_signal_y.setTracking(True)
		self.slider_signal_y.setTickInterval(50)
		self.slider_signal_y.setTickPosition(QSlider.TicksRight)
		self.slider_signal_y.valueChanged.connect(self.SliderValueChanged)

		self.slider_fft_y = QSlider(Qt.Vertical)
		self.slider_fft_y.setRange(0,20)
		self.slider_fft_y.setValue(10)
		self.slider_fft_y.setTracking(True)
		self.slider_fft_y.setTickInterval(1)
		self.slider_fft_y.setTickPosition(QSlider.TicksRight)
		self.slider_fft_y.valueChanged.connect(self.SliderValueChanged_fft)
		
		## Plot
		self.plot, self.curve, self.curve2 = self.create_plot('Time', 'Signal', [0,5,1], [self.yaxis_low,self.yaxis_high,200], ncurves=2)
		ymax = self.slider_fft_y.sliderPosition()/1000.
		self.plot_fft, self.curve_fft, self.curve2_fft = self.create_plot('Frequency [Hz]', 'Power', [0,30,10], [0,0.01,0.005], ncurves=2)
		
		
		## layout
		plot_layout = QGridLayout()#QVBoxLayout()
		plot_layout.addWidget(self.button_start,0,0,1,1)
		plot_layout.addWidget(self.button_stop,0,1,1,1)
		plot_layout.addWidget(self.plot,1,0,2,7)
		plot_layout.addWidget(self.plot_fft,3,0,2,7)
		plot_layout.addWidget(self.slider_signal_y,1,7,2,1)
		plot_layout.addWidget(self.slider_fft_y,3,7,2,1)
		
		plot_groupbox = QGroupBox('Signal')
		plot_groupbox.setLayout(plot_layout)
		
		
		### Arena
		###
		self.plot_arena, self.curve_arena = self.create_arenaplot(' ', 'Y', [-1,1,0.2], [-1,1,0.2], curve_style='o')
		
		self.button_play = QPushButton('Play', self)
		self.button_play.clicked.connect(self.on_arena)
		
		self.button_stgm = QPushButton('Stop Game', self)
		self.button_stgm.clicked.connect(self.on_stop)
		
		self.button_3min = QPushButton('3min Game', self)
		self.button_3min.clicked.connect(self.on_arena)
		
		self.button_gold = QPushButton('Golden Goal', self)
		self.button_gold.clicked.connect(self.on_arena)
		
		plot_layout_arena = QGridLayout()#QVBoxLayout()
		plot_layout_arena.addWidget(self.button_play,0,0)
		plot_layout_arena.addWidget(self.button_stgm,0,1)
		plot_layout_arena.addWidget(self.button_3min,0,2)
		plot_layout_arena.addWidget(self.button_gold,0,3)
		plot_layout_arena.addWidget(self.plot_arena,1,0,4,6)

		plot_groupbox_arena = QGroupBox('Arena')
		plot_groupbox_arena.setLayout(plot_layout_arena)
		
		### Buttons
		###
		
		#layout_buttons = QVBoxLayout(self)
		#layout_buttons.addWidget(self.button)
		
		
		## Main frame and layout
		##
		#self.mdi.addSubWindow(window_buttons)
		self.mdi.addSubWindow(plot_groupbox)
		self.mdi.addSubWindow(plot_groupbox_arena)
		self.setCentralWidget(self.mdi)
		#main_layout.addWidget(plot_groupbox,0,0)
		#main_layout.addWidget(plot_groupbox_arena,0,1,1,1)
		
		#self.main_frame.setLayout(main_layout)
		#self.setGeometry(30, 30, 950, 500)
		
		#self.setCentralWidget(self.main_frame)


	def create_menu(self):
		self.file_menu = self.menuBar().addMenu("&File")
		
		self.start_action = self.create_action("&Start measurement",
			shortcut="Ctrl+M", slot=self.on_start, tip="Start displaying data")
		self.stop_action = self.create_action("&Stop measurement",
			shortcut="Ctrl+T", slot=self.on_stop, tip="Stop displaying data")
		self.start_arena_action = self.create_action("&Start arena",
			shortcut="Ctrl+A", slot=self.on_arena, tip="Start the soccer game")
		self.tiled = self.create_action("&Tile windows",
			shortcut="Ctrl+R", slot=self.tile_windows, tip="Tile open windows")
		exit_action = self.create_action("E&xit", slot=self.close, 
			shortcut="Ctrl+X", tip="Exit the application")
		
		self.start_action.setEnabled(True)
		self.stop_action.setEnabled(False)
		self.start_arena_action.setEnabled(False)
		
		self.add_actions(self.file_menu, 
			(   self.start_action, self.stop_action,
				self.start_arena_action, self.tiled,
				None, exit_action))
			
		self.help_menu = self.menuBar().addMenu("&Help")
		about_action = self.create_action("&About", 
			shortcut='F1', slot=self.on_about, 
			tip='About the monitor')
		
		self.add_actions(self.help_menu, (about_action,))

	def set_actions_enable_state(self):
		start_enable = not self.monitor_active
		stop_enable = self.monitor_active
		start_arena_enable = self.monitor_active
		
		self.start_action.setEnabled(start_enable)
		self.stop_action.setEnabled(stop_enable)
		self.start_arena_action.setEnabled(start_arena_enable)

	def on_about(self):
		msg = __doc__
		QMessageBox.about(self, "About the demo", msg.strip())
	

	def on_stop(self):
		""" Stop the monitor
		"""
		if self.com_monitor is not None:
			self.com_monitor.join(0.01)
			self.com_monitor = None
		
		if self.com_monitor2 is not None:
			self.com_monitor2.join(0.01)
			self.com_monitor2 = None
		
		self.monitor_active = False
		self.timer.stop()
		self.timer_plot.stop()
		self.set_actions_enable_state()
		
		self.status_text.setText('Monitor idle')
	
	def reset_arena(self):
		"""bring ball back to center, remove winner sign"""
		#self.plot_arena.clear()
		self.plot_arena.removeItem(self.winner_text)
		self.show_one_item = False
		
		self.ball_coordx, self.ball_coordy = 0,0
		self.curve_arena.setData([self.ball_coordx], [self.ball_coordy])
		self.playing = False
	
	def reset_signal(self):
		""" empty list of signal values"""
		self.livefeed.updated_list = False
		self.livefeed.list_data = []
		self.livefeed2.updated_list = False
		self.livefeed2.list_data = []
		
		self.curve.setData([], [])
		self.curve_fft.setData([], [])
		self.curve2.setData([], [])
		self.curve2_fft.setData([], [])
		self.plot.replot()
	
	def on_start(self):
		""" Start the monitor: com_monitor thread and the update
			timer
		"""
		if self.com_monitor is not None:
			return
			
		if self.show_one_item is True:
			self.reset_arena()
			self.reset_signal()
		
		self.data_q = Queue.Queue()
		self.error_q = Queue.Queue()
		self.com_monitor = ComMonitorThread(
			self.data_q,
			self.error_q,
			'/dev/ttyACM0',
			230400)
		self.com_monitor.start()
		
		self.data2_q = Queue.Queue()
		self.error2_q = Queue.Queue()
		self.com_monitor2 = ComMonitorThread(
			self.data2_q,
			self.error2_q,
			'/dev/ttyACM1',
			230400)
		self.com_monitor2.start()
		
		com_error = get_item_from_queue(self.error_q)
		com_error2 = get_item_from_queue(self.error2_q)

		if com_error is not None:
			QMessageBox.critical(self, 'ComMonitorThread error',
				com_error)
			self.com_monitor = None
		if com_error2 is not None:
			QMessageBox.critical(self, 'ComMonitorThread error',
				com_error2)
			self.com_monitor2 = None
		
		self.monitor_active = True
		self.set_actions_enable_state()
		
		self.timer = QTimer()
		self.connect(self.timer, SIGNAL('timeout()'), self.on_timer)
		update_freq = 1000. #Hz
		
		self.timer_plot = QTimer()
		self.connect(self.timer_plot, SIGNAL('timeout()'), self.on_timer_plot)
		update_freq_plot = 10. #Hz
		
		self.timer.start(1000.0 / update_freq) #ms
		self.timer_plot.start(1000.0 / update_freq_plot) #ms
		
		self.status_text.setText('Monitor running')
	
	def on_timer(self):
		""" Executed periodically when the monitor update timer
			is fired.
		"""
		self.read_serial_data()
		if self.livefeed.has_new_data:
			self.livefeed.append_data(self.livefeed.read_data())
		
		if self.livefeed2.has_new_data:
			self.livefeed2.append_data(self.livefeed2.read_data())
		#self.update_monitor()
		
	def on_timer_plot(self):
		""" Executed periodically when the plot update timer
			is fired.
		"""
		self.update_monitor()
	
	def on_arena(self):
		if self.monitor_active is False:
			self.on_start()
			
		self.playing = True
		self.ball_coordx, self.ball_coordy = 0,0
		self.curve_arena.setData([self.ball_coordx], [self.ball_coordy])
		print('Game is starting.')
	
	def tile_windows(self):
		self.mdi.tileSubWindows()
	
	def update_monitor(self):
		""" Updates the state of the monitor window with new 
			data. The livefeed is used to find out whether new
			data was received since the last update. If not, 
			nothing is updated.
		"""
		update1, update2 = False,False
		if self.livefeed.updated_list:
			self.temperature_samples = self.livefeed.read_list()

			xdata = [s[0] for s in self.temperature_samples]
			ydata = [s[1] for s in self.temperature_samples]
			
			f = interp1d(xdata, ydata)# alternative (slow) choice: kind='cubic'
			n = len(ydata)
			xdata = np.linspace(xdata[0],xdata[-1],n)
			ydata = f(xdata)
			
			## bandpass filter signal
			ydata = lfilter(self.b, self.a, ydata)
			
			self.plot.setXRange(max(0,xdata[-1]-time_axis_range), max(time_axis_range, xdata[-1]))
			self.curve.setData(xdata, ydata, _CallSync='off')
			
			# plot fft of port 1
			#
			if n>=(self.nmax):
				delta = xdata[1] - xdata[0]
				fft1 = np.abs(np.fft.rfft(ydata))
				fft1 = (fft1/np.sum(fft1))[1:]
				x = np.fft.rfftfreq(n,d=delta)[1:]
				
				self.curve_fft.setData(x,fft1, _CallSync='off')
				
				power_alpha = np.sum(fft1[(x>self.x_low)*(x<self.x_high)])
				update1 = True
			
		if self.livefeed2.updated_list:
			self.temperature_samples2 = self.livefeed2.read_list()

			xdata = [s[0] for s in self.temperature_samples2]
			ydata = [s[1]-50 for s in self.temperature_samples2]
			
			f = interp1d(xdata, ydata)# alternative (slow) choice: kind='cubic'
			n = len(ydata)
			xdata = np.linspace(xdata[0],xdata[-1],n)
			ydata = f(xdata)
			
			## bandpass filter signal
			ydata = lfilter(self.b, self.a, ydata)			
			self.curve2.setData(xdata, ydata, _CallSync='off')
			
			# plot fft of port 2
			#
			if n>=(self.nmax):
				delta = xdata[1] - xdata[0]
				fft1 = np.abs(np.fft.rfft(ydata))
				fft1 = (fft1/np.sum(fft1))[1:]
				x = np.fft.rfftfreq(n,d=delta)[1:]
				
				self.curve2_fft.setData(x,fft1, _CallSync='off')
				
				power_alpha2 = np.sum(fft1[(x>self.x_low)*(x<self.x_high)])
				update2 = True
		
		if (update1 and update2 and self.playing):
			self.ball_coordx += (power_alpha2 - power_alpha)*self.tuning_factor
			self.ball_coordy += np.random.normal(scale=0.05)

			self.curve_arena.setData([np.sign(self.ball_coordx)*min(1, abs(self.ball_coordx))], [self.ball_coordy], _CallSync='off')

			if abs(self.ball_coordy)>(0.7*(1.1-abs(self.ball_coordx))):
				self.ball_coordy = self.ball_coordy - 0.3*self.ball_coordy
			if abs(self.ball_coordx)>1 and self.show_one_item is False:
				winner_color = name_color1 if self.ball_coordx<0 else name_color2
				self.winner_text = pg.TextItem(html=self.text_html.format(winner_color), anchor=(0.5,2.3),\
				border=QColor(winner_color), fill=(201, 165, 255, 100))
				
				self.plot_arena.addItem(self.winner_text)
				self.show_one_item = True
				self.on_stop()
				self.win_hymn_no = np.random.randint(len(sound_files))
				play_sound(sound_path + sound_files[self.win_hymn_no] + '.wav')
	
	def read_serial_data(self):
		""" Called periodically by the update timer to read data
			from the serial port.
		"""
		qdata = list(get_all_from_queue(self.data_q))
		if len(qdata) > 0:
			output = decode_output(qdata[-1][0])
			data = dict(timestamp=qdata[-1][1], 
						temperature=float(np.nanmean(output)))
			self.livefeed.add_data(data)
		
		qdata = list(get_all_from_queue(self.data2_q))
		if len(qdata) > 0:
			output = decode_output(qdata[-1][0])
			data = dict(timestamp=qdata[-1][1], 
						temperature=float(np.nanmean(output)))
			self.livefeed2.add_data(data)
		
		#qdata = list(get_item_from_queue(self.data_q))
		#tstamp = qdata[1]
		#output = decode_output(qdata[0])
		#if len(output) > 0:
			#data = dict(timestamp=tstamp, 
						#temperature=float(np.nanmean(output)))
			#self.livefeed.add_data(data)
			
		#qdata2 = list(get_item_from_queue(self.data2_q))
		#tstamp = qdata2[1]
		#output = decode_output(qdata2[0])
		#if len(output) > 0:
			#data = dict(timestamp=tstamp, 
						#temperature=float(np.nanmean(output)))
			#self.livefeed2.add_data(data)
			

	def add_actions(self, target, actions):
		for action in actions:
			if action is None:
				target.addSeparator()
			else:
				target.addAction(action)

	def create_action(  self, text, slot=None, shortcut=None, 
						icon=None, tip=None, checkable=False, 
						signal="triggered()"):
		action = QAction(text, self)
		if icon is not None:
			action.setIcon(QIcon(":/%s.png" % icon))
		if shortcut is not None:
			action.setShortcut(shortcut)
		if tip is not None:
			action.setToolTip(tip)
			action.setStatusTip(tip)
		if slot is not None:
			self.connect(action, SIGNAL(signal), slot)
		if checkable:
			action.setCheckable(True)
		return action


def main():
	app = QApplication(sys.argv)
	app.setStyle('plastique')
	form = PlottingDataMonitor()
	form.show()
	app.exec_()


if __name__ == "__main__":
	main()
