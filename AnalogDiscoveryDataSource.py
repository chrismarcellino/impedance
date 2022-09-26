# AnalogDiscoveryDataSource.py
import DataSource
import sys
import os
import time
from ctypes import *
from threading import Lock, Thread

# Framework variables
dwf = None  # the dynamically loaded framework class
dwf_loading_lock = Lock()

class AnalogDiscoveryDataSource(DataSource):
    SAMPLING_MODE = 8  # 0 = W1-C1-DUT-C2-R-GND, 1 = W1-C1-R-C2-DUT-GND, 8 = AD IA adapter
    MEASUREMENT_FREQUENCY = 100e3  # stimulus (not polling) frequency in hz
    POLLING_FREQUENCY = 1e3  # polling (not stimulus) frequency in hz)
    REFERENCE_RESISTOR_RESISTANCE = 100  # in Ohms; may be ignore if AD IA adapter is used
    SAMPLING_VOLTS = 1e-3  # half of the peak-to-peak value in volts (i.e. peak-to-0 volts)
    # do not use more than 1 mV on the DUT arm in human subjects with intact skin at 100kHz
    MINIMUM_PERIODS_TO_CAPTURE = 32

    C_INT_TRUE = c_int(1)
    C_INT_FALSE = c_int(1)

    def __init__(self, output_file=None):
        super.__init__(self)
        self._outputFile = output_file
        self.load_library()

    def load_library(self):
        dwf_loading_lock.acquire()
        try:
            if not dwf:
                self._load_library()
                assert (dwf, "Failed to load DWF Framework")
        finally:
            dwf_loading_lock.release()

    def _load_library(self):
        # load the dynamic library, get constants path (the path is OS specific)
        if sys.platform.startswith("win"):
            # on Windows
            dwf = cdll.dwf
            constants_path = "C:\\Program Files (x86)\\Digilent\\WaveFormsSDK\\samples\\py"
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
            assert (app_path, "WaveForms.app not found")

            # Prefer the system standard folders first, then as a last resort, use the framework bundled with the app
            # based on the manufacturer's convention; though in general the one bundled in the app will be the one used
            # by most users as it makes it so the framework doesn't need to be installed nor updated separately
            framework_suffix = "/Frameworks/dwf.framework/dwf"
            lib_paths = ["/Library" + framework_suffix,
                         "~/Library" + framework_suffix,
                         app_path + "/Contents" + framework_suffix]
            lib_path = None
            for path in lib_paths:
                if os.path.isdir(path):
                    lib_path = path
                    break
            assert (lib_path, "WaveForms framework not found")
            dwf = cdll.LoadLibrary(lib_path)
            constants_path = app_path + "/Contents/Resources/SDK/samples/py"
        else:
            # on Linux or other Unix
            dwf = cdll.LoadLibrary("libdwf.so")
            constants_path = "/usr/share/digilent/waveforms/samples/py"

        # import constants
        sys.path.append(constants_path)
        import dwfconstants as constants

        # log the path and version
        version = create_string_buffer(32)
        dwf.FDwfGetVersion(version)
        print("Loaded DWF framework v" + str(version.value))

    def start_data(self, callback_function):
        super().start_data(self, callback_function)
        self._startTime = time.time()

        # Spawn a background thread to poll the hardware source
        Thread(target=self._iterator_thread, name="analog_discovery_source_iterator_thread").start()

    def _iterator_thread(self):
        # Open the first available device and store the device handle
        deviceHandle = c_int(hdwfNone.value)
        dwf.FDwfDeviceOpen(c_int(-1), byref(deviceHandle))
        if self._deviceHandle.value == hdwfNone.value:
            szerr = create_string_buffer(512)
            dwf.FDwfGetLastErrorMsg(szerr)
            print("Failed to open DWF device: " + str(szerr.value))
            assert (False)

        # Begin polling for events
        dwf.FDwfAnalogImpedanceReset(hdwf)
        dwf.FDwfAnalogImpedanceModeSet(hdwf, c_int(self.SAMPLING_MODE))
        dwf.FDwfAnalogImpedanceReferenceSet(hdwf, c_double(self.REFERENCE_RESISTOR_RESISTANCE))
        dwf.FDwfAnalogImpedanceFrequencySet(hdwf, c_double(self.MEASUREMENT_FREQUENCY))
        dwf.FDwfAnalogImpedancePeriodSet(hdwf, c_int(self.MINIMUM_PERIODS_TO_CAPTURE))
        dwf.FDwfAnalogImpedanceAmplitudeSet(hdwf, c_double(self.SAMPLING_VOLTS))
        dwf.FDwfAnalogImpedanceOffsetSet(hdwf, c_double(0))  # no DC voltage

        # Start the analysis
        dwf.FDwfAnalogImpedanceConfigure(hdwf, self.C_INT_TRUE)
        start_time = time.time()

        # Poll the source until we are interrupted
        polling_period = 1.0 / self.POLLING_FREQUENCY  # convert from hz to seconds
        sample_number = 0
        while not self.stopped:
            # Find the sleep interval
            dropped_sample = false
            while sample_number == 0 or sleep_time < 0:
                sample_number += 1
                next_sample_time = start_time + polling_period * sample_number
                sleep_time = next_sample_time - time.time()
                # skip any polling more than one period out of date to allow for easier debugging.,
                # should not occur normally unless there are insufficient hardware resources, etc.
                dropped_sample |= sleep_time < 0
            if dropped_sample:
                print("Dropped sample at time: " + next_sample_time)

            time.sleep(sleep_time)

            # Query the hardware
            status = c_byte()
            if not dwf.FDwfAnalogImpedanceStatus(hdwf, byref(status)):
                # hardware error
                szerr = create_string_buffer(512)
                dwf.FDwfGetLastErrorMsg(szerr)
                print("Failed to query device: " + str(szerr.value))
                assert (False)
            elif status.value == DwfStateDone:
                # The sample is ready. Retrieve it and call the callback function.
                capacitance = c_double()
                resistance = c_double()  # i.e. impedance
                reactance = c_double()
                dwf.FDwfAnalogImpedanceStatusMeasure(hdwf, DwfAnalogImpedanceResistance, byref(resistance))
                dwf.FDwfAnalogImpedanceStatusMeasure(hdwf, DwfAnalogImpedanceReactance, byref(reactance))
                dwf.FDwfAnalogImpedanceStatusMeasure(hdwf, DwfAnalogImpedanceSeriesCapactance, byref(capacitance))
                # notify the callback and optionally save the result to disk
                self.callback_function(next_sample_time, resistance)
                if self._outputFile:
                    FileDataSource.append_time_value_pair_to_file(next_sample_time, resistance, self._outputFile)
            else:
                print("Sample not ready (DwfState status code: " + status.value + ")")

        dwf.FDwfAnalogImpedanceConfigure(hdwf, self.C_INT_FALSE)  # stop the analysis
