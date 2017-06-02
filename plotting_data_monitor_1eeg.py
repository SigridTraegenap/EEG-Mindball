""" 
A simple demonstration of a serial port monitor that plots live
data using pyqtgraph.
The monitor expects to receive 8-byte data packets on the 
serial port. The packages are decoded such that the first byte
contains the 3 most significant bits and the second byte contains
the 7 least significat bits.
"""
import random, sys
import numpy as np
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import pyqtgraph as pg
import Queue

from com_monitor import ComMonitorThread
from libs.utils import get_all_from_queue, get_item_from_queue
from libs.decode import decode_output
from livedatafeed import LiveDataFeed


color1 = "limegreen"
width_signal = 5
time_axis_range = 2 ## in s

pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')
#fixes to white background and black labels


class PlottingDataMonitor(QMainWindow):
	def __init__(self, parent=None):
		super(PlottingDataMonitor, self).__init__(parent)
		
		self.monitor_active = False
		self.com_monitor = None
		self.livefeed = LiveDataFeed()
		self.temperature_samples = []
		self.timer = QTimer()
		
		self.create_menu()
		self.create_main_frame()
		self.create_status_bar()
		
		## spectrum boundaries
		self.x_low = 0.1
		self.x_high = 3
		
		## init arena stuff
		self.ball_coordx = 0.
		self.ball_coordy = 0.
		self.tuning_factor = 0.5
		self.text_html = '<div style="text-align: center"><span style="color: #FFF; font-size: 40pt">Goal</span><br><span style="color: #FFF; font-size: 40pt; text-align: center"> {} is winner </span></div>'
		self.show_one_item = False
		self.winner_text = None
	
	def create_plot(self, xlabel, ylabel, xlim, ylim, ncurves=1):
		plot = pg.PlotWidget()
		curve = plot.plot(antialias=True)
		curve.setPen((200,200,100))
		plot.setLabel('left', ylabel)
		plot.setLabel('bottom', xlabel)
		plot.setXRange(xlim[0], xlim[1])
		plot.setYRange(ylim[0], ylim[1])

		#plot.setCanvasBackground(Qt.black)
		plot.replot()
		
		pen = QPen(QColor(color1))
		#pen.setWidth(0.9)
		curve.setPen(pen)
		
		if ncurves==2:
			curve2 = plot.plot(symbol=curve_style)
			#pen.setWidth(0.9)
			pen2 = QPen(QColor('magenta'))
			curve2.setPen(pen2)
			return plot, curve, curve2
		else:
			return plot, curve
	
	def create_arenaplot(self, xlabel, ylabel="Player "+color1, xlim=[-1,1], ylim=[-1,1], curve_style=None):
		plot = pg.PlotWidget(background=QColor("#217300"))
		if curve_style is not None:
			curve = plot.plot(symbol=curve_style, antialias=True, symbolSize=15, symbolBrush='w')
		else:
			curve = plot.plot(antialias=True)
		plot.setLabel('left', ylabel)
		plot.setLabel('bottom', xlabel)
		plot.setXRange(xlim[0], xlim[1])
		plot.setYRange(ylim[0], ylim[1])
		plot.replot()
		
		spi = pg.ScatterPlotItem(size=15, pen=pg.mkPen(None), brush=pg.mkBrush(255,255,255,0))
		spi.addPoints([{'pos' : [0,0], 'data' : 1, 'pen' : 'w'}])
		plot.addItem(spi)
		
		central_line = pg.GraphItem()
		plot.addItem(central_line)
		pos = np.array([[0.,-1.],[0.,1.],[-1.,0.2],[-0.85,0.2],[-0.85,-0.2],[-1.,-0.2],[1,0.2],[0.85,0.2],[0.85,-0.2],[1,-0.2]])
		adj = np.array([[0,1],[2,3],[3,4],[4,5],[6,7],[7,8],[8,9]])
		lines = np.array([(255,255,255,255,1)]*7,dtype=[('red',np.ubyte),('green',np.ubyte),('blue',np.ubyte),('alpha',np.ubyte),('width',float)])
		central_line.setData(pos=pos,adj=adj,pen=lines,size=0.1)
		
		return plot, curve
	
	def create_status_bar(self):
		self.status_text = QLabel('Monitor idle')
		self.statusBar().addWidget(self.status_text, 1)

	def create_main_frame(self):
		# Main frame and layout
		#
		self.main_frame = QWidget()
		main_layout = QGridLayout()
		#main_layout.setSpacing(3)
		#main_layout.setRowStretch(1, 2)
		main_layout.setColumnStretch(1, 2)


		## Plot
		##
		self.plot, self.curve = self.create_plot('Time', 'Signal', [0,5], [0,1000])
		self.plot_fft, self.curve_fft = self.create_plot('Frequency', 'FFt', [0,75], [0,0.01])
		
		plot_layout = QVBoxLayout()
		plot_layout.addWidget(self.plot)
		plot_layout.addWidget(self.plot_fft)
		
		plot_groupbox = QGroupBox('Signal')
		plot_groupbox.setLayout(plot_layout)
		
		### Arena
		###
		self.plot_arena, self.curve_arena = self.create_arenaplot(' ', 'Y', [-1,1,0], [-1,1,0], curve_style='o')
		
		plot_layout_arena = QHBoxLayout()
		plot_layout_arena.addWidget(self.plot_arena)
		
		plot_groupbox_arena = QGroupBox('Arena')
		plot_groupbox_arena.setLayout(plot_layout_arena)

		## Main frame and layout
		##
		main_layout.addWidget(plot_groupbox,0,0)
		main_layout.addWidget(plot_groupbox_arena,0,1,1,1)
		
		self.main_frame.setLayout(main_layout)
		self.setGeometry(30, 30, 950, 300)
		
		self.setCentralWidget(self.main_frame)
		#self.set_actions_enable_state()

	def create_menu(self):
		self.file_menu = self.menuBar().addMenu("&File")

		self.start_action = self.create_action("&Start monitor",
			shortcut="Ctrl+M", slot=self.on_start, tip="Start the data monitor")
		self.stop_action = self.create_action("&Stop monitor",
			shortcut="Ctrl+T", slot=self.on_stop, tip="Stop the data monitor")
		exit_action = self.create_action("E&xit", slot=self.close, 
			shortcut="Ctrl+X", tip="Exit the application")
		
		self.start_action.setEnabled(True)
		self.stop_action.setEnabled(False)
		
		self.add_actions(self.file_menu, 
			(   self.start_action, self.stop_action,
				None, exit_action))
			
		self.help_menu = self.menuBar().addMenu("&Help")
		about_action = self.create_action("&About", 
			shortcut='F1', slot=self.on_about, 
			tip='About the monitor')
		
		self.add_actions(self.help_menu, (about_action,))

	def set_actions_enable_state(self):
		start_enable = not self.monitor_active
		stop_enable = self.monitor_active
		
		self.start_action.setEnabled(start_enable)
		self.stop_action.setEnabled(stop_enable)

	def on_about(self):
		msg = __doc__
		QMessageBox.about(self, "About the demo", msg.strip())
	

	def on_stop(self):
		""" Stop the monitor
		"""
		if self.com_monitor is not None:
			self.com_monitor.join(0.01)
			self.com_monitor = None

		self.monitor_active = False
		self.timer.stop()
		self.set_actions_enable_state()
		
		self.status_text.setText('Monitor idle')
	
	def reset_arena(self):
		"""bring ball back to center, remove winner sign"""
		#self.plot_arena.clear()
		self.plot_arena.removeItem(self.winner_text)
		self.show_one_item = False
		
		self.ball_coordx, self.ball_coordy = 0,0
		self.curve_arena.setData([self.ball_coordx], [self.ball_coordy])
	
	def reset_signal(self):
		""" empty list of signal values"""
		self.livefeed.updated_list = False
		self.livefeed.list_data = []
		self.curve.setData([], [])
		self.curve_fft.setData([], [])
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
			#115200)
		self.com_monitor.start()
		
		com_error = get_item_from_queue(self.error_q)
		if com_error is not None:
			QMessageBox.critical(self, 'ComMonitorThread error',
				com_error)
			self.com_monitor = None

		self.monitor_active = True
		self.set_actions_enable_state()
		
		self.timer = QTimer()
		self.connect(self.timer, SIGNAL('timeout()'), self.on_timer)
		update_freq = 1000. #Hz
		self.timer.start(1000.0 / update_freq) #ms
		
		self.timer_plot = QTimer()
		self.connect(self.timer_plot, SIGNAL('timeout()'), self.on_timer_plot)
		update_freq = 10. #Hz
		self.timer_plot.start(1000.0 / update_freq) #ms
		
		self.status_text.setText('Monitor running')
		
	def on_timer(self):
		""" Executed periodically when the monitor update timer
			is fired.
		"""
		self.read_serial_data()
		if self.livefeed.has_new_data:
			self.livefeed.append_data(self.livefeed.read_data())
	
	def on_timer_plot(self):
		self.update_monitor()

	
	def update_monitor(self):
		""" Updates the state of the monitor window with new 
			data. The livefeed is used to find out whether new
			data was received since the last update. If not, 
			nothing is updated.
		"""
		update1 = False
		if self.livefeed.updated_list:
			self.temperature_samples = self.livefeed.read_list()
			
			xdata = [s[0] for s in self.temperature_samples]
			ydata = [s[1] for s in self.temperature_samples]
			
			self.plot.setXRange(max(0,xdata[-1]-time_axis_range), max(time_axis_range, xdata[-1]))
			self.curve.setData(xdata, ydata, _CallSync='off')
			
			# plot fft of port 1
			#
			delta = np.array(xdata[1:])-np.array(xdata[:-1])
			#print(np.nanmean(delta))#,np.nanstd(delta))
			n = len(ydata)
			fft1 = np.abs(np.fft.rfft(ydata))
			fft1 = (fft1/np.sum(fft1))[1:]
			x = np.fft.rfftfreq(n,d=np.nanmean(delta))[1:]

			self.curve_fft.setData(x,fft1)
			self.plot_fft.replot()
			
			power_alpha = np.sum(fft1[(x>self.x_low)*(x<self.x_high)])
			#print(power_alpha)
			
			if n>999:
				#print((power_alpha)*self.tuning_factor)
				self.ball_coordx += (power_alpha)*self.tuning_factor
				self.ball_coordy += np.random.normal(scale=0.05)

			self.curve_arena.setData([np.sign(self.ball_coordx)*min(1, abs(self.ball_coordx))], [self.ball_coordy], _CallSync='off')

			if abs(self.ball_coordy)>0.7:
				self.ball_coordy = self.ball_coordy - 0.3*self.ball_coordy
			if abs(self.ball_coordx)>1 and self.show_one_item is False:
				winner_color = color1
				self.winner_text = pg.TextItem(html=self.text_html.format(winner_color), anchor=(0.3,1.3),\
				border=QColor(winner_color), fill=(201, 165, 255, 100))
				
				self.plot_arena.addItem(self.winner_text)
				self.show_one_item = True
				self.on_stop()
			
	
	def read_serial_data(self):
		""" Called periodically by the update timer to read data
			from the serial port.
		"""
		#qdata = list(get_all_from_queue(self.data_q))
		#if len(qdata) > 0:
			#data = dict(timestamp=qdata[-1][1], 
						#temperature=decode_output(qdata[-1][0]))
			#self.livefeed.add_data(data)
		
		qdata = list(get_item_from_queue(self.data_q))
		tstamp = qdata[1]
		output = decode_output(qdata[0])
		if len(output) > 0:
			data = dict(timestamp=tstamp, 
						temperature=float(np.nanmean(output)))
			self.livefeed.add_data(data)
			
	# The following two methods are utilities for simpler creation
	# and assignment of actions
	#
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
	form = PlottingDataMonitor()
	form.show()
	app.exec_()


if __name__ == "__main__":
	main()
