# AnalogDiscoveryDataSource.py
import DataSource
import ctypes
import sys
import os


class AnalogDiscoveryDataSource(DataSource):
    SAMPLING_MODE = 8                           # 0 = W1-C1-DUT-C2-R-GND, 1 = W1-C1-R-C2-DUT-GND, 8 = AD IA adapter
    SAMPLING_FREQUENCY = 100e3                  # in seconds
    REFERENCE_RESISTOR_RESISTANCE = 100         # in Ohms; may be ignore if AD IA adapter is used
    SAMPLING_VOLTS = 1e-3                       # half of the peak-to-peak value in volts (i.e. peak-to-0 volts)
    # do not use more than 1 mV on the DUT arm in human subjects with intact skin at 100kHz
    MINIMUM_PERIODS_TO_CAPTURE = 32

    # Framework variables
    dwf = None  # the dynamically loaded framework class
    dwf_loading_lock = Lock()

    def __init__(self, output_file=None):
        super.__init__(self)
        self._outputFile = output_file
        self._deviceHandle = ctypes.c_int(hdwfNone.value)
        self._deviceName = ""
        self.load_library()

    def load_library(self):
        dwf_loading_lock.acquire()
        try:
            if not dwf:
                _load_library()
                assert(dwf, "Failed to load DWF Framework")
        finally:
          dwf_loading_lock.release()

    def _load_library(self):
        # load the dynamic library, get constants path (the path is OS specific)
        if sys.platform.startswith("win"):
            # on Windows
            dwf = ctypes.cdll.dwf
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
            dwf = ctypes.cdll.LoadLibrary(lib_path)
            constants_path = app_path + "/Contents/Resources/SDK/samples/py"
        else:
            # on Linux or other Unix
            dwf = ctypes.cdll.LoadLibrary("libdwf.so")
            constants_path = "/usr/share/digilent/waveforms/samples/py"

        # import constants
        sys.path.append(constants_path)
        import dwfconstants as constants
        
        # log the path and version
        version = create_string_buffer(32)
        dwf.FDwfGetVersion(version)
        print("Loaded DWF framework v" + str(version.value))

    def start_data(self, callback_function):
        # Open the first available device and store the device handle
        dwf.FDwfDeviceOpen(ctypes.c_int(-1), ctypes.byref(self._deviceHandle))
        if self._deviceHandle.value == hdwfNone.value:
            szerr = create_string_buffer(512)
            dwf.FDwfGetLastErrorMsg(szerr)
            print("Failed to open DWF device: " + str(szerr.value))

        # Begin polling for events
        sts = c_byte()
        frequecy = 1e5
        reference = 1e5

        print("Reference: " + str(reference) + " Ohm  Frequency: " + str(
            frequecy / 1e3) + " kHz for picofarad capacitors")
        dwf.FDwfAnalogImpedanceReset(hdwf)
        dwf.FDwfAnalogImpedanceModeSet(hdwf, c_int(SAMPLING_MODE))
        dwf.FDwfAnalogImpedanceReferenceSet(hdwf, c_double(REFERENCE_RESISTOR_RESISTANCE))
        dwf.FDwfAnalogImpedanceFrequencySet(hdwf, c_double(SAMPLING_FREQUENCY))
        dwf.FDwfAnalogImpedancePeriodSet(hdwf, c_int(MINIMUM_PERIODS_TO_CAPTURE))
        dwf.FDwfAnalogImpedanceAmplitudeSet(hdwf, c_double(SAMPLING_VOLTS))
        dwf.FDwfAnalogImpedanceOffsetSet(hdwf, c_double(0))     # no DC voltage

        dwf.FDwfAnalogImpedanceConfigure(hdwf, c_int(1))  # start the analysis

    def stop_data(self):
        dwf.FDwfAnalogImpedanceConfigure(hdwf, c_int(0))  # stop the analysis
