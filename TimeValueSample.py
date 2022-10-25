# TimeValueSample.py
from collections import deque
import numpy as np
import scipy
from dataclasses import dataclass


@dataclass(frozen=True)
class TimeValueSample:
    """Common immutable sample data structure, for future extensibility (i.e. metadata, comments, etc.)"""
    t: float
    v: float
    # reserved: object = None

    # Produce a copy of TimeValueSample copying any future reserved state/metadata.
    def copy_with(self, new_time=None, new_value=None):
        return TimeValueSample(t=new_time if new_time else self.t, v=new_value if new_value else self.v)


class TimeValueSampleQueue:
    """
    Stores a queue of samples with an (approximately) fixed period, discarding any excess (i.e. oversampled)
    values, and optionally filling any blank sample periods with values of numpy.nan. Only the most recent 'duration'
    (in seconds) samples are stored. When resampling occurs, not all sample metadata (if any exists) may be
    preserved. Metadata preservation is guaranteed when copy_samples() 'desired_period' is None.
    """

    def __init__(self, duration):
        self._duration = duration
        self._queue = deque()
        self._filled = False

    def push(self, sample, ignore_out_of_order_samples=False):
        out_of_order = len(self._queue) > 0 and sample.t <= self._queue[-1].t
        if out_of_order and ignore_out_of_order_samples:
            sample = None

        if sample:
            assert not out_of_order, "Samples are not monotonically increasing in time"
            # append the new sample
            self._queue.append(sample)
            # pop any stale samples
            while len(self._queue) > 0 and self._queue[-1].t - self._queue[0].t > self._duration:
                self._queue.popleft()
                self._filled = True

    def clear(self):
        """Clears the queue. This may be useful for generating intermediate plots which are retrospectively revised."""
        self._queue.clear()
        self._filled = False

    @property
    def filled(self):
        return self._filled

    def copy_samples(self, desired_period=None, resample_threshold_proportion=0.50):
        """
        Retrieves a copy of the samples within the duration provided at initialization. If desired_period is provided
        and any sample is missing from the regular period intervals between the starting and ending points, or if
        any sample time has more jitter than the resample_threshold_proportion of desired_period, then the sequence
        will be resampled using an FFT technique to allow for downstream processing with methods that assume complete,
        uniform and even time spacing.
        """
        assert not desired_period or desired_period > 0.0, "desired_period cannot be negative"

        # If empty or alignment/spacing is not important, just return a copy of the queue:
        if not desired_period or len(self._queue) == 0:
            return list(self._queue)

        start_time = self._queue[0].t
        stop_time = self._queue[-1].t
        num_samples = round((stop_time - start_time) / desired_period) + 1
        times = np.array([sample.t for sample in self._queue])
        aligned_times = np.linspace(start_time, stop_time, num_samples, True)

        resample = True
        # See if we can stay on the fast path (assuming no dropped nor extra samples) based on the average error
        if len(aligned_times) == len(self._queue):
            average_error = np.mean(np.subtract(aligned_times, times))
            # in this case, correct the aligned times to more closely match the actual (as opposed to canonical times)
            aligned_times = np.subtract(times, average_error)
            max_error = np.amax(np.subtract(aligned_times, times))
            if max_error < desired_period * resample_threshold_proportion:
                resample = False

        # Generate the result sample list, using the uniform times
        result = []
        if resample or True:
            # This may be expensive. Attempt to align the data to the nearest original sample to preserve any metadata.
            values = np.array([sample.v for sample in self._queue])
            resampled_times_values_tuple = scipy.signal.resample(values, num_samples, times)
            # Make a copy to we can cull as we go to decrease running time (n log n instead of n^2).
            queue = self._queue.copy()
            for v, t in zip(*resampled_times_values_tuple):
                while len(queue) > 0 and queue[0].t < t - desired_period / 2.0:
                    # This should be uncommon as this would indicate extra samples
                    queue.popleft()
                if len(queue) > 0 and queue[0].t < t + desired_period / 2.0:
                    aligned_sample = queue.popleft().copy_with(t, v)
                else:
                    aligned_sample = TimeValueSample(t, v)
                result.append(aligned_sample)
        else:
            for aligned_time, sample in zip(aligned_times, self._queue):
                aligned_sample = sample.copy_with(new_time=aligned_time)
                result.append(aligned_sample)

        return result
