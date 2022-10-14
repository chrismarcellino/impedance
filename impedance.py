# impedance.py
__version__ = '0.1'

import sys
import argparse
import threading

from PySide6.QtCore import *
from PySide6.QtWidgets import QApplication

from AnalogDiscoveryDataSource import AnalogDiscoveryDataSource
from FileDataSource import FileDataSource
from DataProcessor import DataProcessor
from GUI import GUI


@Slot(float, float)
def data_event_callback(t, v):      # main thread slot call back
    assert threading.current_thread() is threading.main_thread()
    # for the file source, a negative time will indicate the end of the file
    if t < 0:
        app.exit(0)
    data_processor.data_callback(t, v)
    gui.data_callback(t, v)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Chest impedance processor for venous air embolism and other findings.')
    parser.add_argument('-r', '--replay', help='replay impedance input using a previously saved CSV file path')
    parser.add_argument('-s', '--save', help='save impedance measurements to a CSV file path')
    parser.add_argument('--no-gui', help='supress the graphical interface', action='store_true')
    parser.add_argument('-v', '--version', action='version', version='%(prog)s ' + __version__)
    args = parser.parse_args()

    file = None
    if args.replay:
        # Replay a prior recording
        try:
            with open(args.replay, "r") as file:
                source = FileDataSource(file)
        except FileNotFoundError:
            print(f"Path {args.replay} not found.")
            sys.exit(1)
        except IOError as e:
            print(f"I/O error({e.errno}): {e.strerror}")
            sys.exit(1)
    else:
        # If requested, create a file handle to output the recordings
        if args.save:
            try:
                file = open(args.save, "w")
            except FileNotFoundError:
                print(f"Path {args.save} not found.")
                sys.exit(1)
            except IOError as e:
                print(f"I/O error({e.errno}): {e.strerror}")
                sys.exit(1)

        # Open the oscilloscope source, optionally saving the recording
        source = AnalogDiscoveryDataSource(file)

    # In order to unify the event loop dependent code, we use the Qt event loop regardless of whether a GUI
    # is actually shown since it is about as official of a Python run loop as can be found (given the ubiquity of Qt)
    # and the need to use it for UI instances as well. We make an Application to get the run loop.
    gui: GUI = None
    if args.no_gui:
        app = QCoreApplication(sys.argv)
    else:
        app = QApplication(sys.argv)
        gui = GUI()
        gui.create_gui()

    # Create the data processing class
    data_processor: DataProcessor = DataProcessor()

    # Create a signal
    class DataEvent(QObject):
        delivered = Signal(float, float)
    data_event = DataEvent()
    # Register for the signal (on the main thread)
    data_event.delivered.connect(data_event_callback)
    # Start the data collection/replay. The data source will call back on an arbitrary thread but the signal will
    # be queued onto the main thread. See comment in DataSource.start_data().
    source.start_data(data_event.delivered.emit)

    # Start the event loop. This won't return until the GUI is closed or the event loop is exit.
    ret = app.exec()
    if file:            # for syntactical posterity; exiting will do the same
        file.close()
    sys.exit(ret)
