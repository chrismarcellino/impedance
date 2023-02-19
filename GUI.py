# GUI.py
import time
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import pyqtgraph
import numpy as np

from DataProcessor import GraphicalDebuggingDelegate
from TimeValueSample import TimeValueSampleQueue


class GUI(GraphicalDebuggingDelegate):
    MAIN_PLOT_TIME_WIDTH = 20.0  # in seconds
    MAX_REFRESH_RATE = 1.0 / 30.0  # in seconds
    UNPROCESSED_PLOT_DATA_COLOR = 'g'
    PROCESSED_PLOT_DATA_COLORS = ['r', 'b', 'c', 'm', 'y', 'w']
    ABSOLUTE_MAX_VALUE_SCALE = 300.0
    FFT_MAX_VALUE_SCALE = 5.0

    def __init__(self):
        self.view = pyqtgraph.GraphicsView()
        self.layout = pyqtgraph.GraphicsLayout(border=(100, 100, 100))
        self.view.setCentralItem(self.layout)
        self.view.setWindowTitle('Impedance')
        self.view.resize(1100, 700)

        # These are the plots, stacked vertically, in order from top to bottom.
        self.plots = []
        self.plots_without_padding = []

        # Data received in the past MAIN_PLOT_TIME_WIDTH seconds
        self.sample_queue = TimeValueSampleQueue(self.MAIN_PLOT_TIME_WIDTH)
        self.graphical_debugging_sample_queues = {}  # dictionary of labels to queues
        self.needs_redraw = False
        self.last_draw_time = None

    def create_and_layout_plot(self, plot_title=None, absolute=False, fft=False) -> pyqtgraph.PlotItem:
        plot = self.layout.addPlot(title=plot_title, enableMenu=False)
        self.layout.nextRow()
        # Disable interaction
        plot.getViewBox().setMouseEnabled(False, False)
        if absolute:
            plot.getViewBox().setYRange(0.0, self.ABSOLUTE_MAX_VALUE_SCALE)  # Disable Y scaling
        if fft:
            plot.getViewBox().setYRange(0.0, self.FFT_MAX_VALUE_SCALE)
        # We set the fact that this is an FFT plot using a 'custom' instance variable we set on the plot
        plot.impedance_fft = fft
        # Create the unprocessed data plot (the other plots for debugging data are created dynamically).
        self.create_plot_data_item(plot, self.UNPROCESSED_PLOT_DATA_COLOR)
        return plot

    def create_plot_data_item(self, plot, color='w'):
        plot_data_item = plot.plot(pen=color)

        if plot.impedance_fft:
            plot_data_item.setFftMode(True)
            plot_data_item.setPen(pyqtgraph.mkPen(width=2, color=color))
            plot_data_item.setFillLevel(0)
            plot_data_item.setFillBrush(pyqtgraph.mkBrush(color))

    def show_ui(self):
        # Make the plot
        cropped_plot = self.create_and_layout_plot("Cropped")
        absolute_plot = self.create_and_layout_plot("Absolute", absolute=True)
        fft_plot = self.create_and_layout_plot("Power Spectrum (FFT)", fft=True)
        # Set the plot arrays for iteration later
        self.plots = [cropped_plot, absolute_plot, fft_plot]
        self.plots_without_padding = [fft_plot]

        self.view.show()
        self.view.closeEvent = self.layout.closeEvent = lambda event: QApplication.instance().exit(0)

    def data_callback(self, sample):
        self.sample_queue.push(sample)
        self.mark_needs_redraw()

    def mark_needs_redraw(self):
        if not self.needs_redraw:
            self.needs_redraw = True

            if self.last_draw_time:
                next_draw_time = self.last_draw_time + self.MAX_REFRESH_RATE
                delay = max(next_draw_time - time.time(), 0.0)
            else:
                delay = 0.0
            QTimer.singleShot(int(delay * 1e3), self.redraw)  # QTimer accepts milliseconds

    def redraw(self):
        assert len(self.plots) > 0, "must create plots before drawing"
        self.needs_redraw = False
        self.last_draw_time = time.time()

        # The first data item corresponds to the unmodified data.
        queues = [self.sample_queue]
        for labels in self.graphical_debugging_sample_queues.keys():
            queues.append(self.graphical_debugging_sample_queues[labels])

        # Iterate through the data items instead of the higher level plots to avoid redundant work.
        oldest_time_allowed = time_to_pad = None
        for i, queue in enumerate(queues):
            t_data, v_data = self.time_value_arrays_for_queue(queue, oldest_time_allowed)
            if i == 0:
                # The first queue is the unmodified data, which sets our starting bound and padding parameters
                oldest_time_allowed = t_data[0]
                # If we do not have a full screen of data yet, pre-pad with np.nan as filler to maintain uniformity.
                time_to_pad = self.MAIN_PLOT_TIME_WIDTH - (t_data[-1] - t_data[0])
            # Iterate through the higher level plots and set the data item data
            for plot in self.plots:
                assert len(queues) == len(plot.listDataItems()), "mismatch in queues and data items"
                data_item = plot.listDataItems()[i]
                if i != 0 or plot in self.plots_without_padding:
                    # Never pass just 1 item since this can't be graphed by FFT methods etc.
                    data_item.setData(t_data if len(t_data) > 1 else [], v_data if len(v_data) else [])
                else:
                    data_item.setData(*self.pad_samples(t_data, v_data, time_to_pad))

    def time_value_arrays_for_queue(self, queue, oldest_time_allowed=None):
        samples = queue.copy_samples()  # don't pass the period since we want to draw the raw data
        t_data = np.empty(len(samples))
        v_data = np.empty(len(samples))
        for i, sample in enumerate(samples):
            t_data[i] = sample.t
            v_data[i] = sample.v

        if oldest_time_allowed:
            if len(t_data) > 0 and oldest_time_allowed > t_data[-1]:
                t_data = v_data = []
            else:
                for i, t in enumerate(t_data):
                    if oldest_time_allowed <= t:
                        t_data = t_data[i:]
                        v_data = v_data[i:]
                        break

        return t_data, v_data

    def pad_samples(self, t_data, v_data, time_to_pad):
        if len(t_data) > 1:
            average_period = np.mean(np.diff(t_data))
            # This is a float precision safe way to see if there are any, and how many samples to add
            samples_to_add = round(time_to_pad / average_period)
            if samples_to_add > 0:
                # we must use np.linspace instead of np.arange to avoid OBO errors due to float precision
                filler_time_values = np.linspace(t_data[0] - time_to_pad, t_data[0], samples_to_add, endpoint=False)
                t_data = np.concatenate([filler_time_values, t_data])
                nans = np.full(len(filler_time_values), np.nan)
                v_data = np.concatenate([nans, v_data])
                assert len(t_data) == len(v_data)

        return t_data, v_data

    # GraphicalDebuggingDelegate methods
    def create_intermediate_sample_data_plot_and_queue(self, label):
        # pick the next color, wrapping around as needed
        color_index = len(self.graphical_debugging_sample_queues) % len(self.PROCESSED_PLOT_DATA_COLORS)
        color = self.PROCESSED_PLOT_DATA_COLORS[color_index]

        # make a new queue and create the plot data item
        queue = TimeValueSampleQueue(self.MAIN_PLOT_TIME_WIDTH)
        self.graphical_debugging_sample_queues[label] = queue
        for plot in self.plots:
            self.create_plot_data_item(plot, color)

    def graph_intermediate_sample_data(self, label, samples, clear_first=False):
        # Get (and create if needed) the queue for this index
        if label not in self.graphical_debugging_sample_queues:
            self.create_intermediate_sample_data_plot_and_queue(label)
        queue = self.graphical_debugging_sample_queues[label]

        if clear_first:
            queue.clear()

        # Add these samples to the queue and mark for redraw. Ensure that any out-of-order data is silently culled as
        # this is purely a debugging utility, and give the best effort to draw intermediate heuristic data.
        for sample in samples:
            queue.push(sample, ignore_out_of_order_samples=True)
        self.mark_needs_redraw()
