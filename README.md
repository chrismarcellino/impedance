# impedance
Anesthesia chest physiology monitoring

# Prerequisites
1) Recent python3 (on macOS, install Xcode and run once to install developer tools so that system python3 is installed)
2) pip3 install scipy PySide6 pygtgraph 
3) Diligent WaveForms SDK (if using an ARM64 Mac i.e. M1/M2, this requires
v. 3.18.16 or newer to allow import of its framework, and may need to be downloaded 
via the beta page https://forum.digilent.com/topic/8908-waveforms-beta-download/).
If using a beta version on macOS, you will receive a quarantine warning upon first launch. In System Settings...
Privacy & Security...Security, permission can be granted to allow the unsigned framework to be opened, and an Open
button will appear on the next launch attempt which will allow persistent authorization. 
