# DataProcessor.py
import math
from abc import ABC, abstractmethod
import numpy as np
from scipy import signal
from dataclasses import dataclass
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


@dataclass(frozen=True)
class RespiratoryCycleData:
    the_min: float
    the_max: float
    min_percentile: float
    max_percentile: float
    timestamp_in_seconds: float
    period_length_in_seconds: float

    def is_timestamp_coincident(self, timestamp_in_seconds):
        return abs(self.timestamp_in_seconds - timestamp_in_seconds) < (self.period_length_in_seconds / 2.0)


class DataProcessor:
    # We process the previous 20 seconds, every 10 seconds, to allow for better respiratory detection while preserving
    # low latency of VAE detection. Any ratio >= 2:1 will ensure every individual respiratory period is analyzed. The
    # former must be at least twice as long as the minimum respiratory period that we wish to analyze (8 BPM = 7.5 s).
    SAMPLE_ANALYSIS_INTERVAL = 20.0
    SAMPLE_ANALYSIS_PERIOD = 10.0

    # We assume that a RR of 8 to 30 would reflect general anesthesia reasonably well across a range of ages, which
    # corresponds to a frequency (period) of 0.13 hz (7.5 s) and 0.5 hz (2 s) respectively.
    MIN_RESPIRATORY_FREQUENCY = 8.0 / 60.0
    MAX_RESPIRATORY_FREQUENCY = 30.0 / 60.0

    MAX_RESPIRATORY_CYCLE_DATA_TO_KEEP = 100

    def __init__(self, sampling_period, graphical_debugging_delegate):
        self.sampling_period = sampling_period
        self.graphical_debugging_delegate = graphical_debugging_delegate
        self.sample_queue = TimeValueSampleQueue(self.SAMPLE_ANALYSIS_INTERVAL)
        self.last_analysis_time = None
        self.respiratory_cycle_datum = []

    def data_callback(self, sample):
        self.sample_queue.push(sample)

        if self.sample_queue.filled and \
                (not self.last_analysis_time or self.last_analysis_time + self.SAMPLE_ANALYSIS_PERIOD < sample.t):
            self.process_samples()
            self.last_analysis_time = sample.t

    def process_samples(self):
        # Using overlapping portions of the signal (see SAMPLE_ANALYSIS_INTERVAL and SAMPLE_ANALYSIS_PERIOD above), we
        # perform an FFT-based spectral density analysis to determine the dominant respiratory frequency (as the
        # respiratory cycle is the dominant signal in the chest impedance measurement, DOI: 10.1109/51.32406).
        # The presence of and amplitude of this signal is used as one of the main contributors to the signal
        # quality index (SQI).
        #
        # If we find a reasonable respiratory waveform component, we then divide up the period into individual periods.
        # Then, the simplest and most accurate method for determining the end-inspiratory and end-expiratory impedance
        # (EII, EEI), is to find the min. and max. of the waveform within each period as we cannot use the actual
        # filtered waveforms as they only very poorly represent the complex nature of the respiratory signal and mask
        # the offset ("DC" component.) However, to reduce noise artifact, we find the 5%- and 95%-ile value. (The
        # comparison of this to the actual min./max. are also used in the SQI.)
        #
        # We then take each period and compare the EEI and EII from that in the prior ...INTERVAL and use this to
        # determine the likelihood of gross air entrainment. An increase in both EEI and EII as opposed to a change in
        # either parameter alone is more suggestive of VAE (or a change in PEEP) as opposed to changes in other
        # mechanical ventilation parameters (namely, tidal volume which would be expected to modify only EII, or an
        # uncommon (except perhaps in a pressure control mode), an increase in PEEP combined with a decrease in TV
        # could cause an isolated increase in EEI. Hence, paired simultaneous changes in EEI and EII will add to the
        # VAE probability. Consistency in any of these values otherwise will add to the SQI. Irregular hand ventilation
        # may impair this technique and will result in a poor SQI.
        #
        # This algorithm begins below:
        debug_graph = self.graphical_debugging_delegate.graph_intermediate_sample_data
        # Get the samples for the past sampling period, resampling if necessary to obtain time-interval aligned data.
        samples = self.sample_queue.copy_samples(desired_period=self.sampling_period)
        first_sample_timestamp_in_seconds = samples[0].t
        # Get the evenly spaced impedance values as a numpy array
        values = np.array([sample.v for sample in samples])

        # Perform FFT-based spectral density analysis on the signal to try to isolate the dominant periodic signal.
        periodogram_freq, power_density = signal.periodogram(values, fs=1.0 / self.sampling_period)
        dominant_frequency = periodogram_freq[np.argmax(power_density)]
        resp_frequency_detected = self.MIN_RESPIRATORY_FREQUENCY <= dominant_frequency <= self.MAX_RESPIRATORY_FREQUENCY

        if resp_frequency_detected:
            print("Respiratory cycle detected with average frequency {0:1.3f} hz and RR {1:1.0f} (/min.)".format(
                dominant_frequency,
                dominant_frequency * 60.0))
        else:
            print("No respiratory cycle detected. (Dominant frequency {0:1.3f} hz".format(dominant_frequency))

        # If we were successful, continue to divide the values into complete sinusoidal periods. Ignore any
        # incomplete periods on the leading or trailing edge as these will be included in the previous or next sampling
        # interval since there is always at least a 2:1 overlap (SAMPLE_ANALYSIS_INTERVAL : SAMPLE_ANALYSIS_PERIOD).
        if resp_frequency_detected:
            period_length_in_seconds = 1.0 / dominant_frequency
            period_length_in_samples = round(period_length_in_seconds / self.sampling_period)

            slices, start_indexes = self.find_period_slices_with_greatest_average_variance(values,
                                                                                           period_length_in_samples)
            for a_slice, timestamp_in_samples in zip(slices, start_indexes):
                timestamp_in_seconds = first_sample_timestamp_in_seconds + timestamp_in_samples * self.sampling_period
                # Avoid adding duplicate data, and assume the prior data is best to keep.
                is_new = True
                for data in reversed(self.respiratory_cycle_datum):
                    if data.is_timestamp_coincident(timestamp_in_seconds):
                        is_new = False
                        break
                if is_new:
                    # Get min, max, 5%- and 95%-ile values for comparison
                    data = RespiratoryCycleData(the_min=np.min(a_slice),
                                                the_max=np.max(a_slice),
                                                min_percentile=np.percentile(a_slice, 5),
                                                max_percentile=np.percentile(a_slice, 95),
                                                timestamp_in_seconds=timestamp_in_seconds,
                                                period_length_in_seconds=period_length_in_seconds)
                    self.respiratory_cycle_datum.append(data)
                    print("Captured respiratory cycle data for cycle starting at {0:1.1f}".format(timestamp_in_seconds))

        # Trim excess data to ensure a bounded computational time/storage
        while len(self.respiratory_cycle_datum) > self.MAX_RESPIRATORY_CYCLE_DATA_TO_KEEP:
            self.respiratory_cycle_datum.pop(0)

        """
        TODO: PLAN
          
           - For some kind of SQI part from these (primarily) based on differences from min/max, inter-sample variation

            -  Notify when BOTH min and max change since these could represent VAE 

            - Can also notify when changes as tidal volume change and temporarily lower SQI x 1 minute

            --LATER: ascertain pattern in FFT based on data post analysis
        """

    def find_period_slices_with_greatest_average_variance(self, values, period_length, steps=3):
        # A respiratory cycle is defined as inhalation followed by exhalation, so the average signal should be higher
        # earlier than later in the period.
        halves = np.array_split(values, 2)
        is_reversed = np.average(halves[0]) < np.average(halves[1])

        # only need to search up to the half-period since the respiratory cycle is periodic of course
        best_slices = best_start_indexes = best_variance = None
        start_fraction = 0.5 if is_reversed else 0.0
        for offset_fraction in np.linspace(start_fraction, start_fraction + 0.5, steps):
            offset = round(period_length * offset_fraction)
            slices, start_indexes = self.slice_values_into_periods(values, period_length, offset)
            variance = np.var(slices)
            if best_variance is None or variance > best_variance:
                best_slices = slices
                best_start_indexes = start_indexes
                best_variance = variance
        return best_slices, best_start_indexes

    def slice_values_into_periods(self, values, period_length, offset=0):
        num_slices = math.floor(len(values) / period_length)
        slices = []
        start_indexes = []
        for i in range(num_slices):
            start = i * period_length + offset
            end = start + period_length
            if end <= len(values):  # only return complete slices
                a_slice = values[start:end]
                slices.append(a_slice)
                start_indexes.append(start)
        return slices, start_indexes

    def copy_samples_with_values(self, samples, new_values):
        new_queue = []
        for sample, new_value in zip(samples, new_values):
            new_sample = sample.copy_with(new_value=new_value)
            new_queue.append(new_sample)
        return new_queue
