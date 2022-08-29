# FileDataSource.py
import json
import time
from threading import Thread
import DataSource


class FileDataSource(DataSource):
    def __init__(self, file):
        super.__init__(self)
        # deserialize the file
        self._index = 0
        self._timeValuePairs = json.load(file)
        self._startTime = None

        # the files should have a list (array) of time, value sub-lists/tuples
        assert isinstance(self._timeValuePairs, list) and len(self._timeValuePairs) > 0, \
            "invalid input file format: not an array"
        # ensure this is a properly formatted file with a list of time-value sub-lists
        for pair in self._timeValuePairs:
            assert isinstance(pair, list) and len(pair) == 2, \
                "invalid input file format: pairs are not arrays with 2 elements"
            assert isinstance(pair[0], float) and isinstance(pair[1], float), \
                "invalid input file format: pairs are not floats"

    def start_data(self, callback_function):
        super().start_data(self, callback_function)
        self._startTime = time.time()

        # spawn a background thread to simulate the thread-model of the hardware data source(s) to improve code coverage
        Thread(target=self._iterator_thread, name="data_source_iterator_thread").start()

    def _iterator_thread(self):
        for pair in self._timeValuePairs:
            # since this is a dedicated worker thread, just sleep until the next simulated polling time
            original_time_offset_after_start = self._timeValuePairs[self._index] - self._timeValuePairs[0]
            sleep_until_time = self._startTime + original_time_offset_after_start
            sleep_duration = max(sleep_until_time - time.time(), 0)
            time.sleep(sleep_duration)

            # call the callback with the current pair
            if not self.stopped:
                self.callback_function(pair[0], pair[1])

    @staticmethod
    def save_data_source_to_file(times, values, file):
        assert len(times) == len(values) and len(times) > 0
        pairs = []
        for t, v in zip(times, values):
            pairs.append([float(t), float(v)])
        json.dump(pairs, file)
