# GUI.py
from PySide6.QtWidgets import QApplication
import pyqtgraph
import numpy


class GUI:
    DATA_POINTS_TO_GRAPH = 1
    MAIN_PLOT_TIME_WIDTH = 10 # seconds

    def __init__(self):
        self.view = pyqtgraph.GraphicsView()
        self.layout = pyqtgraph.GraphicsLayout(border=(100, 100, 100))
        self.view.closeEvent = self.layout.closeEvent = QApplication.instance().exit(0)
        self.view.setCentralItem(self.layout)
        self.view.setWindowTitle('impedance')
        self.view.resize(800, 600)      # TODO persist last size? must be an automatic way to do so?
        self.plot_list = []

    def showUI(self):
        for i in range(self.DATA_POINTS_TO_GRAPH):
            new_plot = self.layout.addPlot()
            new_plot.plot(numpy.zeros(1000 * self.MAIN_PLOT_TIME_WIDTH))   # this is assuming ms samples TODO
            self.plot_list.append(new_plot.listDataItems()[0])
            self.layout.nextRow()

        self.view.show()

    def data_callback(self, t, v):
        stream_data = [v]  # TODO ignore t for now but obviously we should to graph this more accurately at some point
        for newData, line in zip(stream_data, self.plot_list):
            xData = numpy.arange(len(line.yData))
            yData = numpy.roll(line.yData, -1)
            yData[-1] = newData
            line.setData(xData, yData)
