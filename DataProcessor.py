# DataProcessor.py
from typing import List
from abc import ABC, abstractmethod
import sys
import os
import math
import numpy as np
from scipy import signal
from dataclasses import dataclass
from TimeValueSample import TimeValueSample, TimeValueSampleQueue


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
    timestamp: float    #
    cycle_duration: float

    def is_timestamp_coincident(self, timestamp):
        """
        Returns yes if the argument timestamp refers to the start of a respiratory cycle that is consistent with the
        receiver. Note that a large margin of error is used to avoid false-positives without significant risk of
        false-negatives.
        """
        return abs(self.timestamp - timestamp) < (self.cycle_duration / 2.0)


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

    MAX_RESPIRATORY_CYCLE_DATA_TO_KEEP = 15     # of approximately SAMPLE_ANALYSIS_INTERVAL length, i.e. 5 minutes

    MIN_PLAUSIBLE_IMPEDANCE = 10
    MAX_PLAUSIBLE_IMPEDANCE = 500

    def __init__(self, sampling_period, graphical_debugging_delegate):
        self.sampling_period = sampling_period
        self.graphical_debugging_delegate = graphical_debugging_delegate
        self.sample_queue = TimeValueSampleQueue(self.SAMPLE_ANALYSIS_INTERVAL)
        self.last_analysis_time = None
        # Result data
        self.detected_respiratory_period_length = None      # in seconds; None implies respiratory cycle not detected.
        self.first_detected_respiratory_cycle_time = None   # in seconds; reflects the beginning of the sample interval
        self.respiratory_cycle_data: List[RespiratoryCycleData] = []

    def data_callback(self, sample):
        self.sample_queue.push(sample)

        # Only process samples once we have enough data, and the SAMPLE_ANALYSIS_PERIOD has elapsed (see above.)
        # The queue is limited to SAMPLE_ANALYSIS_INTERVAL samples (see its initialization.)
        if self.sample_queue.filled and \
                (not self.last_analysis_time or self.last_analysis_time + self.SAMPLE_ANALYSIS_PERIOD < sample.t):
            # Call the processing methods
            self.process_samples()
            self.calculate_scores()

            self.last_analysis_time = sample.t

    """
    Using overlapping portions of the signal (see SAMPLE_ANALYSIS_INTERVAL and SAMPLE_ANALYSIS_PERIOD above), we
    perform an FFT-based spectral density analysis to determine the dominant respiratory frequency (as the
    respiratory cycle is the dominant signal in the chest impedance measurement, DOI: 10.1109/51.32406).
    The presence of and amplitude of this signal is used as one of the main contributors to the signal
    quality index (SQI).

    If we find a reasonable respiratory waveform component, we then divide up the period into individual periods.
    Then, the simplest and most accurate method for determining the end-inspiratory and end-expiratory impedance
    (EII, EEI), is to find the min. and max. of the waveform within each period as we cannot use the actual
    filtered waveforms as they only very poorly represent the complex nature of the respiratory signal and mask
    the offset ("DC" component.) However, to reduce noise artifact, we find the 5%- and 95%-ile value. (The
    comparison of this to the actual min./max. are also used in the SQI.)

    We then take each period and compare the EEI and EII from that in the prior …INTERVAL and use this to
    determine the likelihood of gross air entrainment. An increase in both EEI and EII as opposed to a change in
    either parameter alone is more suggestive of VAE (or a change in PEEP) as opposed to changes in other
    mechanical ventilation parameters (namely, tidal volume which would be expected to modify only EII, or an
    uncommon (except perhaps in a pressure control mode), an increase in PEEP combined with a decrease in TV
    could cause an isolated increase in EEI. Hence, paired simultaneous changes in EEI and EII will add to the
    VAE probability. Consistency in any of these values otherwise will add to the SQI. Irregular hand ventilation
    may impair this technique and will result in a poor SQI.
    
    This algorithm is implemented through the following process_sample() and calculate_scores() methods, and their
    subroutines. 
    """
    def process_samples(self):
        # Get the samples for the past sampling period, resampling if necessary to obtain time-interval aligned data.
        samples = self.sample_queue.copy_samples(desired_period=self.sampling_period)
        self.graphical_debugging_delegate.graph_intermediate_sample_data("Uniform", samples)
        # Get the evenly spaced, possibly resampled, impedance values as a numpy array
        values = np.array([sample.v for sample in samples])

        # Determine the average to reject grossly non-physiological data (i.e. disconnection)
        average = np.average(values)
        average_plausible = self.MIN_PLAUSIBLE_IMPEDANCE < average < self.MAX_PLAUSIBLE_IMPEDANCE

        # Perform FFT-based spectral density analysis on the signal to try to isolate the dominant periodic signal.
        periodogram_freq, power_density = signal.periodogram(values, fs=1.0 / self.sampling_period)
        dominant_frequency = periodogram_freq[np.argmax(power_density)]

        # If we were successful, continue to divide the values into complete sinusoidal periods. Ignore any
        # incomplete periods on the leading or trailing edge as these will be included in the previous or next sampling
        # interval since there is always at least a 2:1 overlap (SAMPLE_ANALYSIS_INTERVAL : SAMPLE_ANALYSIS_PERIOD).
        first_sample_timestamp = samples[0].t
        if average_plausible and self.MIN_RESPIRATORY_FREQUENCY <= dominant_frequency <= self.MAX_RESPIRATORY_FREQUENCY:
            print("Respiratory cycle detected with average frequency {:1.3f} hz (RR {:1.0f}).".format(
                dominant_frequency,
                dominant_frequency * 60.0))

            self.detected_respiratory_period_length = 1.0 / dominant_frequency  # in seconds
            # Mark the first contiguous time of detection for SQI purposes
            if not self.first_detected_respiratory_cycle_time:
                self.first_detected_respiratory_cycle_time = first_sample_timestamp

            period_length_in_samples = round(self.detected_respiratory_period_length / self.sampling_period)
            slices, start_indexes = self.find_period_slices_with_greatest_average_variance(values,
                                                                                           period_length_in_samples)
            for a_slice, slice_start_index in zip(slices, start_indexes):
                timestamp = first_sample_timestamp + slice_start_index * self.sampling_period
                # Avoid adding duplicate data, and assume the prior data is best to keep.
                is_new = True
                for data in reversed(self.respiratory_cycle_data):
                    if data.is_timestamp_coincident(timestamp):
                        is_new = False
                        break
                if is_new:
                    self.store_data_for_new_slice(a_slice, timestamp)

            # In the future, can also attempt to look for global "signature-based" evidence of VAE and store that as
            # instance variable state to be accounted for the VAE calculations here.
        else:
            if average_plausible:
                print(f"No respiratory cycle detected. (Dominant frequency {dominant_frequency:1.3f} hz)")
            else:
                print(f"No patient data detected; check cabling and connections. (Avg. impedance: {average:1.3f} ohms)")
            self.detected_respiratory_period_length = None
            self.first_detected_respiratory_cycle_time = None

    def store_data_for_new_slice(self, a_slice, timestamp):    # timestamp is in seconds
        # Get min, max, 5%- and 95%-ile values for comparison
        data = RespiratoryCycleData(the_min=np.min(a_slice),
                                    the_max=np.max(a_slice),
                                    min_percentile=np.percentile(a_slice, 5),
                                    max_percentile=np.percentile(a_slice, 95),
                                    timestamp=timestamp,
                                    cycle_duration=self.detected_respiratory_period_length)
        self.respiratory_cycle_data.append(data)

        # Graph the min. and max. for debugging purposes
        debug_graph_samples = 100   # add arbitrary points within the segment to smooth the graphing
        for i in range(debug_graph_samples):
            offset = self.detected_respiratory_period_length * i / debug_graph_samples
            debug_graph = self.graphical_debugging_delegate.graph_intermediate_sample_data
            debug_graph("Respiratory minimum peaks", [TimeValueSample(t=timestamp + offset, v=data.the_min)])
            debug_graph("Respiratory maximum peaks", [TimeValueSample(t=timestamp + offset, v=data.the_max)])
            debug_graph("Respiratory 5%-ile", [TimeValueSample(t=timestamp + offset, v=data.min_percentile)])
            debug_graph("Respiratory 95%-ile", [TimeValueSample(t=timestamp + offset, v=data.max_percentile)])

        # Trim excess data to ensure a bounded computational time/storage (should only loop once at most)
        while len(self.respiratory_cycle_data) > self.MAX_RESPIRATORY_CYCLE_DATA_TO_KEEP:
            self.respiratory_cycle_data.pop(0)

    def calculate_scores(self):
        # both values defined to be in [0,100]
        vae_score: int = 0
        sqi: int = 0
        sqi_alarm = False

        # Calculate the VAE score using paired *increases* in both the min. and max. (percentile) values to suggest
        # air entrainment with stable mechanical ventilation. Compare the current value to the last 10 respirations
        score_last_number_of_datas = 10
        if len(self.respiratory_cycle_data) > 2:
            recent_datas_except_current = self.respiratory_cycle_data[-score_last_number_of_datas:-1]
            current_data = self.respiratory_cycle_data[-1]
            min_percentiles = np.array([data.min_percentile for data in recent_datas_except_current])
            average_min_percentile = np.average(min_percentiles)
            max_percentiles = np.array([data.max_percentile for data in recent_datas_except_current])
            average_max_percentile = np.average(max_percentiles)

            min_increase = current_data.min_percentile - average_min_percentile
            max_increase = current_data.max_percentile - average_max_percentile
            if min_increase > 0 and max_increase > 0:
                # TODO: NEED TO INVESTIGATE FACTORS TO USE HERE FOR "10"
                vae_score += round((min_increase + max_increase) / 10.0 * 50)
                ratio = max_increase / min_increase
                if ratio > 1.0:
                    ratio = 1.0 / ratio
                vae_score += round(max(1.0 - ratio, 0.0) * 50)

        # SQI is defined as zero if there is no respiratory cycle detectable (throughout the entire past interval)
        if self.detected_respiratory_period_length and len(self.respiratory_cycle_data) > 0:
            # Give up to 50 points purely based on the duration of respiratory history if we are tracking, since we
            # have something to compare.
            sqi += min(len(self.respiratory_cycle_data) * 50 / score_last_number_of_datas, 50)

            # Give additional points (up to 20 points) for long term stability
            time_tracking = self.respiratory_cycle_data[-1].timestamp - self.first_detected_respiratory_cycle_time
            sqi += round(max(time_tracking / 6.0, 20))  # one point per 6 seconds, up to 2 minutes

            # Calculate the remainder of the SQI based on stability in the last MAX_RESPIRATORY_CYCLE_DATA_TO_KEEP
            # intervals of data, however if we are alarming, we can also give points to avoid lowering SQI due to
            # variations simply reflective of VAE to reduce the risk of false negative (i.e. be conservative and alarm).
            # This should allow for lower scores temporarily in other circumstances such as ventilation changes and
            # movement.
            min_percentiles = np.array([data.min_percentile for data in self.respiratory_cycle_data])
            max_percentiles = np.array([data.max_percentile for data in self.respiratory_cycle_data])
            percentile_variances = np.var(min_percentiles) + np.var(max_percentiles)
            percentile_sqi_component = max(1.0 - percentile_variances / 10.0, 0.0) * 10     # the weight

            mins = np.array([data.the_min for data in self.respiratory_cycle_data])
            maxs = np.array([data.the_max for data in self.respiratory_cycle_data])
            absolute_variances = np.var(mins) + np.var(maxs)
            absolute_sqi_component = max(1.0 - absolute_variances / 10.0, 0.0) * 5          # the weight

            tidal_volume_surrogate = max_percentiles - min_percentiles      # in units of Ohms
            tidal_volume_variance = np.var(tidal_volume_surrogate)
            tidal_volume_variance_sqi_component = max(1.0 - tidal_volume_variance / 10.0, 0.0) * 15  # the weight

            aggregate_trend_sqi_component = round(percentile_sqi_component +
                                                  absolute_sqi_component +
                                                  tidal_volume_variance_sqi_component)
            if sqi_alarm and aggregate_trend_sqi_component < 20:
                aggregate_trend_sqi_component += 10
            sqi += aggregate_trend_sqi_component

        # In lieu of supporting output to a clinical monitor via serial, log the current data to the console.
        print(f"Current VAE score: {vae_score} (SQI {sqi})")
        if sqi_alarm:
            self.sound_alarm()

    def sound_alarm(self):
        if sys.platform.startswith("darwin"):
            os.system('say "air embolism alert"')
        else:
            print("\a")  # play a simple bell for non-Mac users (a production design would feed into a clinical monitor)

    # Utility methods
    def find_period_slices_with_greatest_average_variance(self, values, period_length, steps=5):
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
