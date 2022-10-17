# AnalogDiscoveryDataSource.py
from TimeValueSample import TimeValueSample
from DataSource import DataSource
from FileDataSource import FileDataSource
import sys
import os
import time
from threading import Lock, Thread
from dwfconstants import *


class AnalogDiscoveryDataSource(DataSource):
    # Constants
    SAMPLING_MODE = 8  # 0 = W1-C1-DUT-C2-R-GND, 1 = W1-C1-R-C2-DUT-GND, 8 = AD IA adapter
    MEASUREMENT_FREQUENCY = 100e3  # DUT stimulus (not polling) frequency in hz that the impedance is measured at
    POLLING_FREQUENCY = 1e3  # polling frequency (in hz) that determines how often the impedance above is measured
    POLLING_PERIOD = 1.0 / POLLING_FREQUENCY          # converted from hz to seconds
    REFERENCE_RESISTOR_RESISTANCE = 100  # in Ohms; may be ignored if AD IA adapter is used
    SAMPLING_VOLTS = 1e-3  # half of the peak-to-peak value in volts (i.e. peak-to-0 volts)
    # do not use more than 1 mV on the DUT in human subjects with intact skin at 100kHz (total voltage may be higher)
    MINIMUM_PERIODS_TO_CAPTURE = 32  # to average

    C_INT_TRUE = c_int(1)
    C_INT_FALSE = c_int(0)

    # Framework (class) variables
    dwf = None  # the dynamically loaded framework class
    dwf_loading_lock = Lock()

    def __init__(self, output_file=None):
        super().__init__()
        self._outputFile = output_file
        self.load_library()

    @classmethod
    def load_library(cls):
        cls.dwf_loading_lock.acquire()
        try:
            if not cls.dwf:
                cls.dwf = cls._load_library()
                assert cls.dwf, "Failed to load DWF Framework"
        finally:
            cls.dwf_loading_lock.release()

    @classmethod
    def _load_library(cls):
        # load the dynamic library, get constants path (the path is OS specific)
        if sys.platform.startswith("win"):
            # on Windows
            dwf = cdll.dwf
        elif sys.platform.startswith("darwin"):
            # on macOS; find the app path first
            default_app_path = "/Applications/WaveForms.app"
            app_paths = [default_app_path, "~" + default_app_path]
            # query Spotlight to find any alternate locations as well
            stream = os.popen('mdfind "kMDItemKind == Application && kMDItemDisplayName == \'WaveForms\'"')
            app_paths.extend(stream.read().splitlines())
            app_path = None
            for path in app_paths:
                if os.path.isdir(path):
                    app_path = path
                    break
            assert app_path, "WaveForms.app not found"

            # Prefer the system standard folders first, then as a last resort, use the framework bundled with the app
            # based on the manufacturer's convention; though in general the one bundled in the app will be the one used
            # by most users as it makes it so the framework doesn't need to be installed nor updated separately
            framework_suffix = "/Frameworks/dwf.framework/dwf"
            lib_paths = ["/Library" + framework_suffix,
                         "~/Library" + framework_suffix,
                         app_path + "/Contents" + framework_suffix]
            lib_path = None
            for path in lib_paths:
                if os.path.isfile(path):
                    lib_path = path
                    break
            assert lib_path, "WaveForms framework not found"
            dwf = cdll.LoadLibrary(lib_path)
        else:
            # on Linux or other Unix
            dwf = cdll.LoadLibrary("libdwf.so")

        # log the path and version
        version = create_string_buffer(32)
        dwf.FDwfGetVersion(version)
        print("Loaded DWF framework version", version.value.decode("utf-8"))
        return dwf

    def expected_sampling_period(self) -> float:
        return self.POLLING_PERIOD

    def start_data(self, callback_function):
        super().start_data(callback_function)
        # Spawn a background thread to poll the hardware source
        Thread(target=self._polling_thread, name="analog_discovery_source_iterator_thread").start()

    def _open_device(self):
        # Open the first available device and store the device handle
        device_handle = c_int(hdwfNone.value)
        last_error_string = None
        while True:
            self.dwf.FDwfDeviceOpen(c_int(-1), byref(device_handle))
            if device_handle.value == hdwfNone.value:
                error_string = create_string_buffer(512)
                self.dwf.FDwfGetLastErrorMsg(error_string)
                if error_string.value != last_error_string:
                    print("Failed to open Analog Discovery device. Error code:",
                          error_string.value.decode("utf-8").splitlines())
                    print("Awaiting device connection")
                    last_error_string = error_string.value
                time.sleep(1)
            else:
                break

        print("Connected to Analog Discovery device with handle:", device_handle.value)
        return device_handle

    def _polling_thread(self):
        dwf = self.dwf  # typing convenience
        # Open the first available device and store the device handle
        device_handle = self._open_device()

        # Begin polling for events
        dwf.FDwfAnalogImpedanceReset(device_handle)
        dwf.FDwfAnalogImpedanceModeSet(device_handle, c_int(self.SAMPLING_MODE))
        dwf.FDwfAnalogImpedanceReferenceSet(device_handle, c_double(self.REFERENCE_RESISTOR_RESISTANCE))
        dwf.FDwfAnalogImpedanceFrequencySet(device_handle, c_double(self.MEASUREMENT_FREQUENCY))
        dwf.FDwfAnalogImpedancePeriodSet(device_handle, c_int(self.MINIMUM_PERIODS_TO_CAPTURE))
        dwf.FDwfAnalogImpedanceAmplitudeSet(device_handle, c_double(self.SAMPLING_VOLTS))
        dwf.FDwfAnalogImpedanceOffsetSet(device_handle, c_double(0))  # no DC voltage

        # Start the analysis
        dwf.FDwfAnalogImpedanceConfigure(device_handle, self.C_INT_TRUE)
        start_time = time.time()

        # Poll the source until we are interrupted
        polling_period = self.POLLING_PERIOD
        sample_number, next_sample_time = 0, 0
        while not self.stopped:
            # Find the sleep interval
            sleep_time = 0
            dropped_sample = False
            while sample_number == 0 or sleep_time < 0:
                sample_number += 1
                next_sample_time = start_time + polling_period * sample_number
                sleep_time = next_sample_time - time.time()
                # skip any polling more than one period out of date to allow for easier debugging.,
                # should not occur normally unless there are insufficient hardware resources, etc.
                dropped_sample |= sleep_time < 0
            if dropped_sample:
                print("Dropped sample at time: {:.3f}".format(next_sample_time))

            time.sleep(sleep_time)

            # Query the hardware
            status = c_byte()
            if not dwf.FDwfAnalogImpedanceStatus(device_handle, byref(status)):
                # hardware error
                error_string = create_string_buffer(512)
                dwf.FDwfGetLastErrorMsg(error_string)
                print("Failed to query device: ", error_string.value)
                exit(1)
            elif status.value == DwfStateDone:
                # The sample is ready. Retrieve it and call the callback function.
                impedance = c_double()
                dwf.FDwfAnalogImpedanceStatusMeasure(device_handle, DwfAnalogImpedanceResistance, byref(impedance))
                # notify the callback and optionally save the result to disk
                sample = TimeValueSample(next_sample_time, impedance.value)
                self.callback_function(sample)
                if self._outputFile:
                    FileDataSource.append_time_value_pair_to_file(sample, self._outputFile)
            else:
                print("Sample not ready; DwfState status code:", status.value)

        dwf.FDwfAnalogImpedanceConfigure(device_handle, self.C_INT_FALSE)  # stop the analysis
