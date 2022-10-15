# GUI.py
import time
from PySide6.QtCore import *
from PySide6.QtWidgets import QApplication
import pyqtgraph
import numpy as np


class GUI:
    MAIN_PLOT_TIME_WIDTH = 10      # in seconds
    FILLER_TIME_PERIOD = 0.001     # in seconds
    MAX_REFRESH_RATE = 1.0 / 60.0  # in seconds

    def __init__(self):
        self.view = pyqtgraph.GraphicsView()
        self.layout = pyqtgraph.GraphicsLayout(border=(100, 100, 100))
        self.view.setCentralItem(self.layout)
        self.view.setWindowTitle('Impedance')
        self.view.resize(900, 700)

        # These are the plots, stacked vertically, in order from top to bottom.
        self.plots = []
        self.plots_without_padding = []

        # Data received in the past MAIN_PLOT_TIME_WIDTH seconds
        self.samples = []
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
        # Store the data first, then trim any excess values
        self.samples.append(sample)
        while self.samples[-1].t - self.samples[0].t > self.MAIN_PLOT_TIME_WIDTH:
            self.samples.pop(0)
        # Mark the view as requiring redraw
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

        # Generate the new data to draw, which may include pre-padding to keep uniformity
        x_data_no_padding = np.array([sample.t for sample in self.samples])
        y_data_no_padding = np.array([sample.v for sample in self.samples])

        data_duration = self.samples[-1].t - self.samples[0].t
        time_to_pad = self.MAIN_PLOT_TIME_WIDTH - data_duration
        if time_to_pad > self.FILLER_TIME_PERIOD:
            filler_time_values = np.arange(self.samples[0].t - time_to_pad, self.samples[0].t, self.FILLER_TIME_PERIOD)
            x_data = np.concatenate([x_data_no_padding, filler_time_values])
            nans = np.empty(len(filler_time_values))
            nans[:] = np.nan
            y_data = np.concatenate([y_data_no_padding, nans])
            assert len(x_data) == len(y_data)
        else:
            x_data = x_data_no_padding
            y_data = y_data_no_padding

        for plot in self.plots:
            for data_item in plot.listDataItems():
                if plot in self.plots_without_padding:
                    data_item.setData(x_data_no_padding, y_data_no_padding)
                else:
                    data_item.setData(x_data, y_data)
