# DataProcessor.py
from abc import ABC, abstractmethod
import numpy as np
from scipy import signal
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

    def __init__(self, sampling_period, graphical_debugging_delegate):
        self.sampling_period = sampling_period
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
        debug_graph = self.graphical_debugging_delegate.graph_intermediate_sample_data
        # Get the samples for the past sampling period, resampling if necessary to obtain time-interval aligned data.
        samples = self.sample_queue.copy_samples(desired_period=self.sampling_period)
        # Get just the evenly spaced impedance values.
        values = np.array([sample.v for sample in samples])

        # Perform bandpass to detect respiratory cycle. We assume that a RR of 8 to 24 would reflect general
        # anesthesia reasonably well, which corresponds to a frequency (period) of 0.13 hz (7.5 s) and 0.4 hz (2.5 s)
        # respectively. Spontaneous ventilation and irregular hand ventilation may impair this technique.
        respiratory_bandpass_values = self.butterworth_bandpass_filter(values, 1.0 / 7.5, 1.0 / 2.5)
        # Add back in the DC for plotting onlt
        respiratory_bandpass_values_with_offset = np.add(respiratory_bandpass_values, np.mean(values))
        debug_graph("Respiratory bandpass",
                    self.copy_samples_with_values(samples, respiratory_bandpass_values_with_offset),
                    clear_first=True)

        """
        TODO: PLAN
        -  high pass- low pass (or FFT) over 10 s prior sample to find component in range from freq. of 8 bpm to 30
         bpm, then measure amplitude and offset, to calculate min and max.  
          
           - For some kind of SQI part from this (primarily) based on amplitudes and total other noise. 

            -  Notify when BOTH min and max change since these could represent VAE 

            - Can also notify when changes as tidal volume change and temporarily lower SQI x 1 minute

            --LATER: ascertain pattern in FFT based on data post analysis
        """

    def butterworth_bandpass_filter(self, values, low, high, order=4):
        sos = signal.butter(order, [low, high], btype='bandpass', output='sos', fs=1.0 / self.sampling_period)
        return signal.sosfiltfilt(sos, values)

    def copy_samples_with_values(self, samples, new_values):
        new_queue = []
        for sample, new_value in zip(samples, new_values):
            new_sample = sample.copy_with(new_value=new_value)
            new_queue.append(new_sample)
        return new_queue
