# DataSource.py
from abc import ABC, abstractmethod


class DataSource(ABC):
    def __init__(self):
        self.callback_function = None
        self._stopped = True

    @abstractmethod
    def expected_sampling_period(self):
        """Returns the natural frequency of the datasource"""
        pass

    @abstractmethod
    def start_data(self, callback_function):
        """Starts receiving events from the subclass source.

        callback_function has one argument, a TimeValueSample, which specify the system relative timestamp in seconds
        and the measured impedance corresponding to the timestamp, respectively.

        The FileDataSource will return a Null TimeValueSample at the end of the stream. Other data sources could do the
        same in the event of an unrecoverable error however should generally just wait for further input.

        It is imperative to note that this function will be called on a background thread and clients should use
        appropriate synchronization or event loop message relaying to delegate these events to a main thread. Note that
        a trampoline function or lambda that calls a Tk.after(0, function_or_lambda) message to relay the message to
        the GUI thread is sufficient: https://docs.python.org/3/library/tkinter.html#threading-model otherwise in Qt
        a signal will be required to be emitted via a Qt.QueuedConnection to a main thread, which will be automatically
        used when a slot is fired from another thread in modern Qt versions."""
        self._stopped = False
        self.callback_function = callback_function

    def stop_data(self):
        self._stopped = True
        self._callback_function = None

    @property
    def callback_function(self):
        return self._callback_function

    @callback_function.setter
    def callback_function(self, callback_function):
        self._callback_function = callback_function

    @property
    def stopped(self):
        return self._stopped
