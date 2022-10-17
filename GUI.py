# GUI.py
import time
from PySide6.QtCore import *
from PySide6.QtWidgets import QApplication
import pyqtgraph
import numpy as np

from DataProcessor import GraphicalDebuggingDelegate
from TimeValueSample import TimeValueSampleQueue


class GUI(GraphicalDebuggingDelegate):
    MAIN_PLOT_TIME_WIDTH = 10.0    # in seconds
    MAX_REFRESH_RATE = 1.0 / 30.0  # in seconds
    UNPROCESSED_PLOT_DATA_COLOR = 'g'
    PROCESSED_PLOT_DATA_COLORS = ['r', 'b', 'c', 'm', 'y', 'w']
    ABSOLUTE_MAX_VALUE_SCALE = 300.0

    def __init__(self, expected_sampling_period):
        self.expected_sampling_period = expected_sampling_period

        self.view = pyqtgraph.GraphicsView()
        self.layout = pyqtgraph.GraphicsLayout(border=(100, 100, 100))
        self.view.setCentralItem(self.layout)
        self.view.setWindowTitle('Impedance')
        self.view.resize(900, 700)

        # These are the plots, stacked vertically, in order from top to bottom.
        self.plots = []
        self.plots_without_padding = []

        # Data received in the past MAIN_PLOT_TIME_WIDTH seconds
        self.sample_queue = TimeValueSampleQueue(self.MAIN_PLOT_TIME_WIDTH)
        self.graphical_debugging_sample_queues = {}     # dictionary of labels to queues
        self.needs_redraw = False
        self.last_draw_time = None

    def create_and_layout_plot(self, title=None, absolute=False, fft=False) -> pyqtgraph.PlotItem:
        plot = self.layout.addPlot(title=title, enableMenu=False)
        self.layout.nextRow()
        # Disable interaction
        plot.getViewBox().setMouseEnabled(False, False)
        if absolute:
            plot.getViewBox().setYRange(0.0, self.ABSOLUTE_MAX_VALUE_SCALE)  # Disable Y scaling
        # We set the fact that this is an FFT plot using a 'custom' instance variable we set on the plot
        plot.impedance_fft = fft
        # Create the unprocessed data plot (the other plots for debugging data are created dynamically).
        self.create_plot_data_item(plot, self.UNPROCESSED_PLOT_DATA_COLOR)
        return plot

    def create_plot_data_item(self, plot, color):
        plot_data_item = plot.plot(pen=color)
        if plot.impedance_fft:
            plot_data_item.setFftMode(True)
            plot_data_item.setPen(pyqtgraph.mkPen(width=2, color=color))
            plot_data_item.setFillLevel(0)
            plot_data_item.setFillBrush(pyqtgraph.mkBrush(color))
            plot.getViewBox().setXRange(0.0, 100)  # Disable X scaling

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
            QTimer.singleShot(delay * 1e3, self.redraw)      # QTimer accepts milliseconds

    def redraw(self):
        self.needs_redraw = False
        self.last_draw_time = time.time()

        samples = self.sample_queue.copy_samples()      # don't pass any period since we want to draw the raw data
        t_data = np.array([sample.t for sample in samples])
        v_data = np.array([sample.v for sample in samples])
        # If we do not have a full screen of data yet, we will pre-pad with np.nan as filler to maintain uniformity.
        data_duration = t_data[-1] - t_data[0]
        time_to_pad = self.MAIN_PLOT_TIME_WIDTH - data_duration

        # Iterate over the plots and populate the data
        for plot in self.plots:
            # The first plot data item is the unmodified plots
            data_item = plot.listDataItems()[0]
            if plot in self.plots_without_padding:
                data_item.setData(t_data, v_data)
            else:
                t_data_padded, v_data_padded = self.pad_samples(t_data, v_data, time_to_pad)
                data_item.setData(t_data_padded, v_data_padded)
            # Any subsequent plot data items are intermediate/debugging plots
            """for data_item in plot.listDataItems()[1:]:
                if plot in self.plots_without_padding:
                    data_item.setData(*self.pad_samples(t_data, v_data, time_to_pad))
                else:
                    data_item.setData(t_data, v_data)
                # TODO PASS INT. DATA TO THE PLOT instead of the above"""

    def pad_samples(self, t_data, v_data, time_to_pad):
        if time_to_pad > self.expected_sampling_period:
            filler_time_values = np.arange(t_data[0] - time_to_pad, t_data[0], self.expected_sampling_period)
            t_data = np.concatenate([t_data, filler_time_values])
            nans = np.full(len(filler_time_values), np.nan)
            v_data = np.concatenate([v_data, nans])
            assert len(t_data) == len(v_data)
            #TODO: LENGTHS ARE OBO TO HIGH???

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

    def graph_intermediate_sample_data(self, label, samples):
        # Get (and create if needed) the queue for this index
        if not label in self.graphical_debugging_sample_queues:
            self.create_intermediate_sample_data_plot_and_queue(label)
        queue = self.graphical_debugging_sample_queues[label]

        # Add these samples to the queue and mark for redraw
        for sample in samples:
            queue.push(sample)
        self.mark_needs_redraw()
