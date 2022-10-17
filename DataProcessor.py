# DataProcessor.py
from abc import ABC, abstractmethod
import numpy as np
from TimeValueSample import TimeValueSampleQueue


class GraphicalDebuggingDelegate(ABC):
    @abstractmethod
    def graph_intermediate_sample_data(self, label, samples, clear_first=False):
        """
        Graphs the derived sample data 'sample' for the purposes of validation and debugging. Samples must be an
        iterable type. It need not be a complete set of points to draw though each value provided must be unique and
        monotonically increasing for a given label across all calls to this method, unless clear_first is true, in
        which case all prior sample data are reset and cleared from the plot. The label is both used in the legend and
        also to unique each plot data set.
        """
        pass


class DataProcessor:
    # We process the previous 10 seconds, every 5 seconds, to allow for better respiratory detection while preserving
    # low latency of VAE detection.
    SAMPLE_ANALYSIS_INTERVAL = 10.0
    SAMPLE_ANALYSIS_PERIOD = 5.0

    def __init__(self, expected_sampling_period, graphical_debugging_delegate):
        self.expected_sampling_period = expected_sampling_period
        self.graphical_debugging_delegate = graphical_debugging_delegate
        self.sample_queue = TimeValueSampleQueue(self.SAMPLE_ANALYSIS_INTERVAL)
        self.last_analysis_time = None

    def data_callback(self, sample):
        self.sample_queue.push(sample)

        if self.sample_queue.filled and \
                (not self.last_analysis_time or self.last_analysis_time + self.SAMPLE_ANALYSIS_PERIOD < sample.t):
            self.process_samples()
            self.last_analysis_time = sample.t

    def process_samples(self):
        samples = self.sample_queue.copy_samples(desired_period=self.expected_sampling_period)
        # TODO do the magic, and call the graphical_debugging_delegate at each interesting step; REMOVE TESTING
        test_samples = []
        for sample in samples:
            test_sample = sample.copy_with(new_value=sample.v * 0.9)     # test code to graph a difference
            test_samples.append(test_sample)
        self.graphical_debugging_delegate.graph_intermediate_sample_data("Test half for no reason!", test_samples, clear_first=True)
        # END TEMP TESTING CODE
