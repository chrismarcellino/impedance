# TimeValueSample.py
from collections import deque
import numpy as np
import scipy
from dataclasses import dataclass


# Common immutable sample data structure, for future extensibility (i.e. metadata, comments, etc.)
@dataclass(frozen=True)
class TimeValueSample:
    t: float
    v: float

    # reserved: object = None

    # Produce a copy of TimeValueSample copying any future reserved state/metadata.
    def copy_with_time(self, new_t, new_v=None):
        return TimeValueSample(new_t, new_v if new_v else self.v)


# Stores a queue of samples with an (approximately) fixed period, discarding any excess (i.e. oversampled)
# values, and optionally filling any blank sample periods with values of numpy.nan. Only the most recent 'duration'
# (in seconds) samples are stored. When resampling occurs, not all sample metadata (if any exists) may be preserved.
class TimeValueSampleQueue:
    def __init__(self, duration):
        self._duration = duration
        self._queue = deque()

    def push(self, sample):
        assert len(self._queue) == 0 or sample.t > self._queue[-1].t, "Samples are not monotonically increasing in time"
        # append the new sample
        self._queue.append(sample)
        # pop any stale samples
        while len(self._queue) > 0 and self._queue[-1].t - self._queue[0].t > self._duration:
            self._queue.popleft()

    def get_samples(self, desired_period=None, resample_threshold_proportion=0.50):
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
        # See if we can stay on the fast path (if dropped nor extra samples) based on the average error
        if len(aligned_times) == len(self._queue):  # TODO ENSURE THAT ALL MISSES HERE ARE NOT BUGS! HIGH RISK OF OBOE
            average_error = np.mean(np.subtract(aligned_times, times))
            # in this case, correct the aligned times to more closely match the actual (as opposed to canonical times)
            aligned_times = np.subtract(times, average_error)
            max_error = np.amax(np.subtract(aligned_times, times))
            if max_error < desired_period * resample_threshold_proportion:
                resample = False

        # Generate the result sample list, using the uniform times
        result = []
        if resample:
            print("Resampling")       # TODO TEMPORARY COMMENT ME OUT
            # This may be expensive. Attempt to align the data to the nearest original sample to preserve any metadata.
            values = np.array([sample.v for sample in self._queue])
            resampled_times_values_tuple = scipy.signal.resample(values, num_samples, times)
            # Make a copy to we can cull as we go to decrease running time (n log n instead of n^2).
            queue = self._queue.copy()
            for t, v in zip(resampled_times_values_tuple[0], resampled_times_values_tuple[1]):
                while len(queue) > 0 and queue[0].t < t - desired_period / 2.0:
                    # this should be uncommon as this would indicate extra samples
                    print("Dropping sample:", queue[0])      # TODO TEMPORARY COMMENT ME OUT
                    queue.popleft()
                if len(queue) > 0 and queue[0].t < t + desired_period / 2.0:
                    aligned_sample = queue[0].copy_with_time(t, v)
                else:
                    aligned_sample = TimeValueSample(t, v)
                result.append(aligned_sample)
        else:
            for i, sample in enumerate(self._queue):
                aligned_time = aligned_times[i]
                aligned_sample = sample.copy_with_time(aligned_time)
                result.append(aligned_sample)

        return result
