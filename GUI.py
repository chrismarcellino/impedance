# GUI.py
from PySide6.QtWidgets import QApplication
import pyqtgraph
import numpy as np


class GUI:
    MAIN_PLOT_TIME_WIDTH = 10   # in seconds
    FILLER_TIME_PERIOD = 0.001  # in seconds

    def __init__(self):
        self.view = pyqtgraph.GraphicsView()
        self.layout = pyqtgraph.GraphicsLayout(border=(100, 100, 100))
        self.view.closeEvent = self.layout.closeEvent = QApplication.instance().exit()
        self.view.setCentralItem(self.layout)
        self.view.setWindowTitle('impedance')
        self.view.resize(800, 600)  # TODO persist last size? must be an automatic way to do so?

        # These are the plots, stacked vertically, in order from top to bottom.
        self.cropped_plot = None
        self.absolute_plot = None
        self.fft_plot = None  # TODO implement

        # Data received in the past MAIN_PLOT_TIME_WIDTH seconds
        self.t_data = []
        self.v_data = []

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

    def data_callback(self, t, v):
        # Store the data first, then trim any excess values
        self.t_data.append(t)
        self.v_data.append(v)
        while self.t_data[-1] - self.t_data[0] > self.MAIN_PLOT_TIME_WIDTH:
            self.t_data.pop(0)
            self.v_data.pop(0)
        assert len(self.t_data) == len(self.v_data)

        # Generate the new data to draw, which may include pre-padding to keep uniformity
        data_duration = self.t_data[-1] - self.t_data[0]
        time_to_pad = self.MAIN_PLOT_TIME_WIDTH - data_duration
        if time_to_pad > 0.0:
            filler_time_values = np.arange(self.t_data[0] - time_to_pad, self.t_data[0], self.FILLER_TIME_PERIOD)
            x_data = np.concatenate([self.t_data, filler_time_values])
            nans = np.empty(len(filler_time_values))
            nans[:] = np.nan
            y_data = np.concatenate([self.v_data, nans])
            assert len(x_data) == len(y_data)
        else:
            x_data = self.t_data
            y_data = self.v_data

        for plot in [self.cropped_plot, self.absolute_plot]:
            data_item = plot.listDataItems()[0]
            data_item.setData(x_data, y_data)
