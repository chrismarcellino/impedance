# AnalogDiscoveryDataSource.py
import DataSource
import ctypes
import sys
import os


class AnalogDiscoveryDataSource(DataSource):
    def __init__(self, output_file=None):
        super.__init__(self)
        self._dwf = None
        self._outputFile = output_file
        self._deviceHandle = ctypes.c_int(hdwfNone.value)
        self._deviceName = ""
        self.load_library()

    def load_library(self):
        # load the dynamic library, get constants path (the path is OS specific)
        if sys.platform.startswith("win"):
            # on Windows
            self._dwf = ctypes.cdll.dwf
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
            self._dwf = ctypes.cdll.LoadLibrary(lib_path)
            constants_path = app_path + "/Contents/Resources/SDK/samples/py"
        else:
            # on Linux or other Unix
            self._dwf = ctypes.cdll.LoadLibrary("libdwf.so")
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
        self._dwf.FDwfDeviceOpen(ctypes.c_int(-1), ctypes.byref(self._deviceHandle))
        if self._deviceHandle.value == hdwfNone.value:
            szerr = create_string_buffer(512)
            dwf.FDwfGetLastErrorMsg(szerr)
            print("Failed to open DWF device:" + str(szerr.value))


    def stop_data(self):
        pass
