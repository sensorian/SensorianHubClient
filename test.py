#!/usr/bin/python
from __future__ import print_function
import time
import Sensorian_Client

Sensorian_Client.config()
Sensorian_Client.setup()
time.sleep(5)
Sensorian_Client.print_values()
Sensorian_Client.display_values()
time.sleep(15)
Sensorian_Client.cleanup()
