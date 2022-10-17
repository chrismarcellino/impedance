# GUI.py
import time
from PySide6.QtCore import *
from PySide6.QtWidgets import QApplication
import pyqtgraph
import numpy as np
from TimeValueSample import TimeValueSampleQueue


class GUI:
    MAIN_PLOT_TIME_WIDTH = 10.0    # in seconds
    MAX_REFRESH_RATE = 1.0 / 30.0  # in seconds

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
        self.needs_redraw = False
        self.last_draw_time = None

    def create_and_layout_plot_item(self, title=None, color=None, absolute=False, fft=False):
        plot_item = self.layout.addPlot(title=title, enableMenu=False)
        self.layout.nextRow()
        # Disable interaction
        plot_item.getViewBox().setMouseEnabled(False, False)
        # Set the color and other options
        plot_data_item = plot_item.plot(pen=color)
        if absolute:
            plot_item.getViewBox().setYRange(0.0, 300)  # Disable Y scaling
        if fft:
            plot_data_item.setFftMode(True)
            plot_data_item.setPen(pyqtgraph.mkPen(width=5, color=color))
            plot_data_item.setFillLevel(0)
            plot_data_item.setFillBrush(pyqtgraph.mkBrush(color))
            plot_item.getViewBox().setXRange(0.0, 100)  # Disable X scaling
        return plot_item

    def show_ui(self):
        # Make the plot
        cropped_plot = self.create_and_layout_plot_item("Cropped", color='red')
        absolute_plot = self.create_and_layout_plot_item("Absolute", color='orange', absolute=True)
        fft_plot = self.create_and_layout_plot_item("Power Spectrum (FFT)", color='green', fft=True)
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

        samples = self.sample_queue.copy_samples(desired_period=self.expected_sampling_period)
        t_data = t_data_no_padding = np.array([sample.t for sample in samples])
        v_data = v_data_no_padding = np.array([sample.v for sample in samples])

        # If, we do not have a full screen of data yet, pre-pad with np.nan as filler to maintain uniformity.
        data_duration = samples[-1].t - samples[0].t
        time_to_pad = self.MAIN_PLOT_TIME_WIDTH - data_duration
        if time_to_pad > self.expected_sampling_period:
            filler_time_values = np.arange(samples[0].t - time_to_pad, samples[0].t, self.expected_sampling_period)
            t_data = np.concatenate([t_data_no_padding, filler_time_values])
            nans = np.full(len(filler_time_values), np.nan)
            v_data = np.concatenate([v_data_no_padding, nans])
            assert len(t_data) == len(v_data)

        for plot in self.plots:
            for data_item in plot.listDataItems():
                if plot in self.plots_without_padding:
                    data_item.setData(t_data_no_padding, v_data_no_padding)
                else:
                    data_item.setData(t_data, v_data)
