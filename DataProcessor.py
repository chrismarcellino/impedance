# DataProcessor.py


class DataProcessor:
    def __init__(self):
        pass

    def data_callback(self, t, v):
        print("Received data at %.3f seconds with value %.3f" % (t, v), flush=True)
        # TODO implement data processing
