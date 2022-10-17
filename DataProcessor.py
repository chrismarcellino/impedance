# DataProcessor.py
from abc import ABC, abstractmethod
import numpy as np
from TimeValueSample import TimeValueSampleQueue


class GraphicalDebuggingDelegate(ABC):
    @abstractmethod
    def graph_intermediate_sample_data(self, sample, data_index, label=None):
        """
        Graphs the derived sample data 'sample' for the purposes of validation and debugging.
        The data_index is an arbitrary index denoting the relative ordering of the data, for the purposes of legend
        creation and coloring. The label may be used in the legend and should be the same for all samples with the same
        data_index (otherwise one may be arbitrarily chosen.)
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
