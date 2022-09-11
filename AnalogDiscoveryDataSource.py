# AnalogDiscoveryDataSource.py
import DataSource


class AnalogDiscoveryDataSource(DataSource):
    def __init__(self, file):
        super.__init__(self)
        self._outputFile = file

    def start_data(self, callback_function):
        pass

    def stop_data(self):
        pass
