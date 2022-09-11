# GUI.py
import tkinter as tk


class GUI:
    def __init__(self):
        pass

    def create_gui(self, ws):
        # TODO temporary filler implementation; implement UI
        ws.title('Impedance')
        ws.geometry('300x200')
        ws.config(bg='#4a7a8c')
        tk.Button(ws, text='Exit', command=lambda: ws.destroy()).pack(expand=True)
