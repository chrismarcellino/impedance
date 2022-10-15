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
        self.view.resize(800, 600)  # TODO persist last size? must be an automatic way to do so?

        # These are the plots, stacked vertically, in order from top to bottom.
        self.cropped_plot = None
        self.absolute_plot = None
        self.fft_plot = None  # TODO implement

        # Data received in the past MAIN_PLOT_TIME_WIDTH seconds
        self.samples = []
        self.needs_redraw = False
        self.last_draw_time = None

    def create_and_layout_line_plot(self, title):
        new_plot = self.layout.addPlot(title=title)
        new_plot.plot()
        # Add it to the layout
        self.layout.nextRow()

        return new_plot

    def show_ui(self):
        self.cropped_plot = self.create_and_layout_line_plot("Cropped")
        self.absolute_plot = self.create_and_layout_line_plot("Absolute")

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
                delay = next_draw_time - time.time()
            else:
                delay = 0.0

            QTimer.singleShot(delay * 1e3, self.redraw)      # QTimer accepts milliseconds

    def redraw(self):
        self.needs_redraw = False
        self.last_draw_time = time.time()

        # Generate the new data to draw, which may include pre-padding to keep uniformity
        x_data = np.array([sample.t for sample in self.samples])
        y_data = np.array([sample.v for sample in self.samples])

        data_duration = self.samples[-1].t - self.samples[0].t
        time_to_pad = self.MAIN_PLOT_TIME_WIDTH - data_duration
        if time_to_pad > 0.0:
            filler_time_values = np.arange(self.samples[0].t - time_to_pad, self.samples[0].t, self.FILLER_TIME_PERIOD)
            x_data = np.concatenate([x_data, filler_time_values])
            nans = np.empty(len(filler_time_values))
            nans[:] = np.nan
            y_data = np.concatenate([y_data, nans])
            assert len(x_data) == len(y_data)

        for plot in [self.cropped_plot, self.absolute_plot]:
            data_item = plot.listDataItems()[0]
            data_item.setData(x_data, y_data)
