# FileDataSource.py
import csv
import time
from threading import Thread
from DataSource import DataSource
from TimeValueSample import TimeValueSample


class FileDataSource(DataSource):
    TIME_CSV_COLUMN = 0
    VALUE_CSV_COLUMN = 1

    def __init__(self, file):
        super().__init__()
        # deserialize the file
        self._startTime = None

        # Ensure this is a properly formatted file with rows of time-value pairs, and copy them out to a list for
        # random access.
        time_value_pairs_csv = csv.reader(file, quoting=csv.QUOTE_NONNUMERIC)
        self._timeValueSamples = []
        for pair in time_value_pairs_csv:
            # ignore extra elements (which could be comments or other metadata)
            assert len(pair) >= 2, "invalid input file format: rows are not arrays with at least 2 elements"
            t = pair[self.TIME_CSV_COLUMN]
            v = pair[self.VALUE_CSV_COLUMN]
            assert isinstance(t, float) and isinstance(v, float), "invalid input file format: pairs are not numerical"
            self._timeValueSamples.append(TimeValueSample(t, v))

    def start_data(self, callback_function):
        super().start_data(callback_function)
        self._startTime = time.time()

        # Spawn a background thread to simulate the thread-model of the hardware data source(s) to improve code coverage
        Thread(target=self._iterator_thread, name="data_source_iterator_thread").start()

    def _iterator_thread(self):
        for sample in self._timeValueSamples:
            # since this is a dedicated worker thread, just sleep until the next simulated polling time
            original_time_offset_after_start = sample.t - self._timeValueSamples[0].t
            sleep_until_time = self._startTime + original_time_offset_after_start
            sleep_duration = max(sleep_until_time - time.time(), 0)
            time.sleep(sleep_duration)

            if self.stopped:
                break
            else:
                # call the callback with the current pair
                self.callback_function(sample)

        # Since we are out of data, send a final sentinel data pair mark our state as stopped.
        if not self.stopped:
            self.callback_function(None)
            self.stop_data()

    @classmethod
    def append_time_value_pair_to_file(cls, t, v, file):
        writer = csv.writer(file, quoting=csv.QUOTE_NONNUMERIC)
        writer.writerow([t, v])
        file.flush()
