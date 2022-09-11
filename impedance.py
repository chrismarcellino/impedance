# impedance.py
__version__ = '0.1'

import sys
import argparse
import tkinter as tk

from AnalogDiscoveryDataSource import AnalogDiscoveryDataSource
from FileDataSource import FileDataSource
from DataProcessor import DataProcessor
from GUI import GUI


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

    # In order to unify the run loop dependent code, we use the Tkinter run loop regardless of whether a GUI
    # is actually shown since it is about as official of a Python run loop as can be found
    tk_container = tk.Tk()
    gui = None
    if not args.no_gui:
        gui = GUI()
        gui.create_gui(tk_container)

    # Create the data processing class
    data_processor: DataProcessor = DataProcessor()

    # Start the data collection/replay. Invoke the callback on the main thread. See comment in DataSource.start_data().
    source.start_data(lambda t, v: tk_container.after(0, data_processor.data_callback(t, v)))
    # Start the run loop
    tk_container.mainloop()

    if file:
        file.close()
