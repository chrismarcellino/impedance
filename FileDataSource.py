# FileDataSource.py
import csv
import time
from threading import Thread
import DataSource


class FileDataSource(DataSource):
    TIME_INDEX = 0
    VALUE_INDEX = 1

    def __init__(self, file):
        super.__init__(self)
        # deserialize the file
        self._index = 0
        self._startTime = None

        # ensure this is a properly formatted file with rows of time-value pairs, and copy them out to a list for
        # random access
        time_value_pairs_csv = csv.reader(file, quoting=csv.QUOTE_NONNUMERIC)
        self._timeValuePairs = []
        for pair in time_value_pairs_csv:
            assert len(pair) == 2, "invalid input file format: rows are not arrays with 2 elements"
            assert isinstance(pair[self.TIME_INDEX], float) and isinstance(pair[self.VALUE_INDEX], float), \
                "invalid input file format: pairs are not numerical"
            self._timeValuePairs.append(tuple(pair))

    def start_data(self, callback_function):
        super().start_data(self, callback_function)
        self._startTime = time.time()

        # Spawn a background thread to simulate the thread-model of the hardware data source(s) to improve code coverage
        Thread(target=self._iterator_thread, name="data_source_iterator_thread").start()

    def _iterator_thread(self):
        for pair in self._timeValuePairs:
            # since this is a dedicated worker thread, just sleep until the next simulated polling time
            original_time_offset_after_start = self._timeValuePairs[self._index][self.TIME_INDEX] - \
                                               self._timeValuePairs[0][self.TIME_INDEX]
            sleep_until_time = self._startTime + original_time_offset_after_start
            sleep_duration = max(sleep_until_time - time.time(), 0)
            time.sleep(sleep_duration)

            # call the callback with the current pair
            if not self.stopped:
                self.callback_function(pair[0], pair[1])

    @staticmethod
    def append_time_value_pair_to_file(t, v, file):
        writer = csv.writer(file, quoting=csv.QUOTE_NONNUMERIC)
        writer.writerow([t, v])
        file.flush()
