#!/usr/bin/python
from __future__ import print_function
from __future__ import division
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import range
from past.utils import old_div
import configparser
import os
import requests
import json
import time
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
import TFT as GLCD
import APDS9300 as LuxSens
import MPL3115A2 as altibar
import CAP1203 as touch
import MCP79410RTCC as rtc
import FXOS8700CQR1 as imuSens
import threading
import socket
import fcntl
import struct
import subprocess
import RPi.GPIO as GPIO
from flask import Flask, abort, request
from flask_restful import Api, Resource, reqparse
from flask_httpauth import HTTPBasicAuth
from multiprocessing import Process

# Sensor initializations

# RTC excepts on first call on boot
# Loops until the RTC works
RTCNotReady = True
while RTCNotReady:
    try:
        RTC = rtc.MCP79410()
        RTCNotReady = False
    except:
        RTCNotReady = True

# LightSensor needs C drivers to turn on
# Currently just part of a cron job, might include here

imuSensor = imuSens.FXOS8700CQR1()
imuSensor.configureAccelerometer()
imuSensor.configureMagnetometer()
imuSensor.configureOrientation()
AltiBar = altibar.MPL3115A2()
AltiBar.ActiveMode()
AltiBar.BarometerMode()
# print "Giving the Barometer 2 seconds or it won't work"
time.sleep(2)
CapTouch = touch.CAP1203()

# Prepare an object for drawing on the TFT LCD
disp = GLCD.TFT()
disp.initialize()
disp.clear()
font = ImageFont.truetype('/usr/share/fonts/truetype/freefont/FreeSansBold.ttf', 14)  # use a truetype font

# Thread sentinels - Threads stop looping when disabled
timeEnabled = True
ambientEnabled = True
lightEnabled = True
cpuEnabled = True
interfaceIPEnabled = True
publicIPEnabled = True
accelEnabled = True
pressureEnabled = True
buttonEnabled = True
sendEnabled = False
flaskEnabled = True

# Global sensor/IP variables protected by locks below if required
currentDateTime = RTC.GetTime()
cpuSerial = "0000000000000000"
light = -1
ambientTemp = -1
cpuTemp = -1
mode = -1
accelX = 0
accelY = 0
accelZ = 0
modeprevious = -1
ambientPressure = -1
watchedInterface = "eth0"
interfaceIP = "0.0.0.0"
publicIP = "0.0.0.0"
serverURL = "http://localhost/"
iftttEvent = "SensorianEvent"
iftttKey = "xxxxxxxxxxxxxxxxxxxxxx"
button = 0
displayEnabled = True
printEnabled = False
lockOrientation = False
defaultOrientation = 0
sleepTime = 1
postInterval = 4
postTimeout = 5
ambientInterval = 5
lightInterval = 1
cpuTempInterval = 5
interfaceInterval = 30
publicInterval = 30
accelInterval = 1
inMenu = False
currentMenu = "Top"
menuElements = []
topMenuElements = ["Exit", "General", "UI", "Requests", "Accelerometer", "Light", "Ambient", "System"]
menuPosition = 0
parser = configparser.SafeConfigParser()
threads = []
killWatch = False

# Board Pin Numbers
INT_PIN = 11    # Ambient Light Sensor Interrupt - BCM 17
LED_PIN = 12    # LED - BCM 18
CAP_PIN = 13    # Capacitive Touch Button Interrupt - BCM 27
GPIO.setmode(GPIO.BOARD)

# Lock to ensure one sensor used at a time
# Sensorian firmware not thread-safe without
I2CLock = threading.Lock()

# Sentinel Thread Locks - Make sure the thread and main program aren't
# accessing the thread sentinels at the same time
timeEnabledLock = threading.Lock()
ambientEnabledLock = threading.Lock()
lightEnabledLock = threading.Lock()
accelEnabledLock = threading.Lock()
interfaceIPEnabledLock = threading.Lock()
publicIPEnabledLock = threading.Lock()
cpuEnabledLock = threading.Lock()
pressureEnabledLock = threading.Lock()
buttonEnabledLock = threading.Lock()
sendEnabledLock = threading.Lock()

# Global Variable Thread Locks - Make sure the thread and main program aren't
# accessing the global sensor variables at the same time
serialLock = threading.Lock()
ambientTempLock = threading.Lock()
lightLock = threading.Lock()
modeLock = threading.Lock()
interfaceLock = threading.Lock()
interfaceIPLock = threading.Lock()
publicIPLock = threading.Lock()
cpuTempLock = threading.Lock()
ambientPressureLock = threading.Lock()
rtcLock = threading.Lock()
buttonLock = threading.Lock()
accelXLock = threading.Lock()
accelYLock = threading.Lock()
accelZLock = threading.Lock()
inMenuLock = threading.Lock()
currentMenuLock = threading.Lock()
menuElementsLock = threading.Lock()
menuPositionLock = threading.Lock()
defaultOrientationLock = threading.Lock()
lockOrientationLock = threading.Lock()
printEnabledLock = threading.Lock()
displayEnabledLock = threading.Lock()
sleepTimeLock = threading.Lock()
postTimeoutLock = threading.Lock()
killWatchLock = threading.Lock()
flaskEnabledLock = threading.Lock()

app = Flask(__name__)
api = Api(app)
auth = HTTPBasicAuth()

@auth.get_password
def get_password(username):
    if username == 'dylan':
        return 'dylanrestpass'
    return None


class ConfigListAPI(Resource):
    decorators = [auth.login_required]

    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument('name', type=str, location='json')
        self.reqparse.add_argument('value', type=str, location='json')
        super(ConfigListAPI, self).__init__()

    def get(self):
        _config_list = get_all_config()
        # for variable in _config_list
        return {'variables': _config_list }
        # return {'variables': [marshal(variable, config_fields) for variable in _config_list]}


class ConfigAPI(Resource):
    decorators = [auth.login_required]

    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument('name', type=str, location='json')
        self.reqparse.add_argument('value', type=str, location='json')
        super(ConfigAPI, self).__init__()

    def get(self, name):
        _config_temp = get_config_value(name)
        if _config_temp != "ConfigNotFound":
            return {'name': name, 'value': _config_temp}
        else:
            abort(404)

    def put(self, name):
        _config_temp = get_config_value(name)
        if _config_temp != "ConfigNotFound":
            args = self.reqparse.parse_args()
            if args['value'] is not None:
                _set_temp = set_config_value(name, args['value'])
                if _set_temp:
                    return {'name': name, 'value': get_config_value(name)}
                else:
                    abort(400, 'Invalid value received, please provide the correct type')
            else:
                abort(400, 'No value received, please provide a value in the JSON')
        else:
            abort(404)


api.add_resource(ConfigListAPI, '/variables', endpoint='variables')
api.add_resource(ConfigAPI, '/variables/<string:name>', endpoint='variable')


def run_flask():
    print("Running Flask")
    app.run(debug=True, use_reloader=False, host='0.0.0.0')


def shutdown_server():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()


@app.route('/shutdown', methods=['POST'])
@auth.login_required
def shutdown_flask_api():
    shutdown_server()
    return 'Flask server shutting down...'


@app.route('/commands/kill', methods=['POST'])
@auth.login_required
def kill_client_api():
    kill_program()
    return 'Sensorian Client shutting down...'


@app.route('/commands/shutdown', methods=['POST'])
@auth.login_required
def shutdown_pi_api():
    shutdown_pi()
    return 'Raspberry Pi shutting down...'


@app.route('/commands/reboot', methods=['POST'])
@auth.login_required
def reboot_pi_api():
    reboot_pi()
    return 'Raspberry Pi rebooting...'


def kill_flask():
    url = 'http://127.0.0.1:5000/shutdown'
    headers = {'Authorization': 'Basic ZHlsYW46ZHlsYW5yZXN0cGFzcw=='}
    try:
        requests.post(url, headers=headers)
    except requests.exceptions.ConnectionError:
        print("Flask server already shut down")


# Updates the global CPU serial variable
def UpdateSerial():
    # Extract serial from cpuinfo file
    global cpuSerial
    tempSerial = "0000000000000000"
    # Get serial from the file, if fails, return error serial
    try:
        f = open('/proc/cpuinfo', 'r')
        for line in f:
            if line[0:6] == 'Serial':
                tempSerial = line[10:26]
        f.close()
    except:
        tempSerial = "ERROR000000000"
    # Update the serial global variable when safe
    finally:
        serialLock.acquire()
        cpuSerial = tempSerial
        serialLock.release()


# Get the most recent update of the serial number when safe
def GetSerial():
    serialLock.acquire()
    tempSerial = cpuSerial
    serialLock.release()
    return tempSerial


# General thread class to repeatedly update a variable at a set interval
class GeneralThread(threading.Thread):
    # Initializes a thread upon creation
    # Takes an artbitrary ID and name of thread, an interval float how often
    # to update the variable, and the method name to call to update it
    def __init__(self, threadID, name, interval, method):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        if (interval < 1):
            self.interval = 1
        else:
            self.interval = interval
        self.method = method
        self.repeat = CheckSentinel(self.method)
        self.slept = 0
        self.toSleep = 0

    def run(self):
        # Thread loops as long as the sentinel remains True
        while (self.repeat):
            methods[self.method]()
            self.slept = 0
            # Keep sleeping until it's time to update again
            while (self.slept < self.interval):
                # Check the global sentinel for this thread every second at most
                self.repeat = CheckSentinel(self.method)
                # If the sentinel changed to false this second, kill the thread
                if (self.repeat == False):
                    print("Killing " + self.name)
                    break
                # If it did not, sleep for another second unless less than a
                # second needs to pass to reach the end of the current loop
                if (self.interval - self.slept < 1):
                    self.toSleep = self.interval - self.slept
                else:
                    self.toSleep = 1
                time.sleep(self.toSleep)
                self.slept = self.slept + self.toSleep


class FlaskThread(threading.Thread):
    # Initializes a thread to run Flask
    def __init__(self):
        threading.Thread.__init__(self)
        self.threadID = 99
        self.name = "FlaskThread"
    def run(self):
        run_flask()
        print("Killing " + self.name)


# Updates the global light variable
def UpdateLight():
    global light
    tempLight = -1
    I2CLock.acquire()
    # Try to initialize and update the light value
    # Sometimes it excepts, so catch it if it does
    try:
        AmbientLight = LuxSens.APDS9300()
        channel1 = AmbientLight.readChannel(1)
        channel2 = AmbientLight.readChannel(0)
        tempLight = AmbientLight.getLuxLevel(channel1, channel2)
    except:
        print("EXCEPTION IN LIGHT UPDATE")
    I2CLock.release()
    # Update the global light level when safe
    lightLock.acquire()
    try:
        light = tempLight
    finally:
        lightLock.release()


# Get the most recent update of the light level when safe
def GetLight():
    lightLock.acquire()
    try:
        tempLight = light
    finally:
        lightLock.release()
    return tempLight


# Get the most recent update of the ambient temperature when safe
def GetAmbientTemp():
    ambientTempLock.acquire()
    returnTemp = ambientTemp
    ambientTempLock.release()
    return returnTemp


# Get the most recent update of the ambient pressure when safe
def GetAmbientPressure():
    ambientPressureLock.acquire()
    returnPress = old_div(float(ambientPressure), 1000)
    ambientPressureLock.release()
    return returnPress


# Update the various barometer/altimeter sensor variables
def UpdateAmbient():
    global ambientTemp
    global ambientPressure
    # Sensor needs some wait time between calls
    time.sleep(0.5)
    # Update the ambient temperature global variable
    I2CLock.acquire()
    temp = AltiBar.ReadTemperature()
    I2CLock.release()
    time.sleep(0.5)
    ambientTempLock.acquire()
    ambientTemp = temp
    ambientTempLock.release()
    # Check to see if pressure is desired
    pressureEnabledLock.acquire()
    tempEnabled = pressureEnabled
    pressureEnabledLock.release()
    # If pressure is needed, update the global variable when safe
    if (tempEnabled):
        I2CLock.acquire()
        press = AltiBar.ReadBarometricPressure()
        I2CLock.release()
        ambientPressureLock.acquire()
        ambientPressure = press
        ambientPressureLock.release()
    else:
        print("NoPressureNeeded")
    # Getting altitude as well would result in additional sleeps
    # for the sensor, may calculate from location/pressure/temp
    '''
    altitudeEnabledLock.acquire()
    tempEnabled = pressureEnabled
    altitudeEnabledLock.release()
    if (tempEnabled):
        I2CLock.acquire()
        alt = AltiBar.ReadBarometricPressure()
        I2CLock.release()
        ambientPressureLock.acquire()
        ambientPressure = press
        ambientPressureLock.release()
    else:
        print "NoAltitudeNeeded"
    '''


# Update the current date and time from the real time clock
def UpdateDateTime():
    global currentDateTime
    I2CLock.acquire()
    tempDateTime = RTC.GetTime()
    I2CLock.release()
    rtcLock.acquire()
    currentDateTime = tempDateTime
    rtcLock.release()


# Get the most recent date and time when safe
def GetDateTime():
    rtcLock.acquire()
    tempDateTime = currentDateTime
    rtcLock.release()
    return tempDateTime


# Update the global variable of the CPU temperature
def UpdateCPUTemp():
    # Read the CPU temperature from the system file
    global cpuTemp
    tPath = '/sys/class/thermal/thermal_zone0/temp'
    tFile = open(tPath)
    cpu = tFile.read()
    tFile.close()
    temp = (old_div(float(cpu), 1000))
    # Update the global variable when safe
    cpuTempLock.acquire()
    cpuTemp = temp
    cpuTempLock.release()


# Get the latest update of the CPU temperature when safe
def GetCPUTemp():
    cpuTempLock.acquire()
    temp = cpuTemp
    cpuTempLock.release()
    return temp


# Update the global variable for the IP of the primary interface
def UpdateWatchedInterfaceIP():
    global interfaceIP
    interfaceLock.acquire()
    tempInterface = watchedInterface
    interfaceLock.release()
    ipaddr = GetInterfaceIP(tempInterface)
    interfaceIPLock.acquire()
    interfaceIP = ipaddr
    interfaceIPLock.release()


# Get the latest IP of the primary interface when safe
def GetWatchedInterfaceIP():
    interfaceIPLock.acquire()
    tempIP = interfaceIP
    interfaceIPLock.release()
    return tempIP


# Get the IP of the passed interface
def GetInterfaceIP(interface):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Try to get the IP of the passed interface
    try:
        ipaddr = socket.inet_ntoa(fcntl.ioctl(
            s.fileno(),
            0x8915,  # SIOCGIFADDR
            struct.pack('256s', interface[:15])
        )[20:24])
    # If it fails, return localhost IP
    except Exception:
        ipaddr = "127.0.0.1"
    return ipaddr


# Update the global variable for current public IP from the icanhazip site
# Don't update too frequently, that's not cool
def UpdatePublicIP():
    global publicIP
    # Initiate a subprocess to run a curl request for the public IP
    proc = subprocess.Popen(["curl", "-s", "-4", "icanhazip.com"], stdout=subprocess.PIPE)
    (out, err) = proc.communicate()
    # Store the response of the request when safe
    publicIPLock.acquire()
    publicIP = out.rstrip()
    publicIPLock.release()


# Get the latest update of the public IP address
def GetPublicIP():
    publicIPLock.acquire()
    tempIP = publicIP
    publicIPLock.release()
    return tempIP


# Update all accelerometer related global variables when safe
def UpdateAccelerometer():
    global mode
    global modeprevious
    global accelX
    global accelY
    global accelZ
    I2CLock.acquire()
    # If the accelerometer is ready, read the orientation and forces
    if (imuSensor.readStatusReg() & 0x80):
        x, y, z = imuSensor.pollAccelerometer()
        orienta = imuSensor.getOrientation()
        I2CLock.release()
        # Store the various global variables when safe
        accelXLock.acquire()
        accelX = x
        accelXLock.release()
        accelYLock.acquire()
        accelY = y
        accelYLock.release()
        accelZLock.acquire()
        accelZ = z
        accelZLock.release()
        modeLock.acquire()
        mode = (orienta >> 1) & 0x03
        modeLock.release()
        if (mode != modeprevious):
            # Alert change in orientation if required
            # print "Changed orientation"
            modeprevious = GetMode()
    else:
        I2CLock.release()


# Get the latest update of the orientation from the global when safe
def GetMode():
    modeLock.acquire()
    tempMode = mode
    modeLock.release()
    return tempMode


# Get the latest update of the X acceleration when safe
def GetAccelX():
    accelXLock.acquire()
    x = accelX
    accelXLock.release()
    return x


# Get the latest update of the Y acceleration when safe
def GetAccelY():
    accelYLock.acquire()
    y = accelY
    accelYLock.release()
    return y


# Get the latest update of the Z acceleration when safe
def GetAccelZ():
    accelZLock.acquire()
    z = accelZ
    accelZLock.release()
    return z


# Update the latest button press to the global variable
def UpdateButton():
    print("You Shouldn't Be Here...")


# Update the button pressed when interrupted
def ButtonEventHandler(pin):
    GPIO.output(LED_PIN, True)
    global button
    I2CLock.acquire()
    tempNewButton = CapTouch.readPressedButton()
    I2CLock.release()
    buttonLock.acquire()
    button = tempNewButton
    buttonLock.release()
    while (tempNewButton == 0):
        I2CLock.acquire()
        tempNewButton = CapTouch.readPressedButton()
        I2CLock.release()
    ButtonHandler(tempNewButton)
    GPIO.output(LED_PIN, False)


# Get the latest update of the most recent button press
def GetButton():
    buttonLock.acquire()
    tempButton = button
    buttonLock.release()
    return tempButton


# Method for the threads to check if their sentinels have changed
def CheckSentinel(sentinel):
    # Check the thread's method name against the statements to
    # find their respective sentinel variables
    if (sentinel == "UpdateDateTime"):
        timeEnabledLock.acquire()
        state = timeEnabled
        timeEnabledLock.release()
    elif (sentinel == "UpdateAmbient"):
        ambientEnabledLock.acquire()
        state = ambientEnabled
        ambientEnabledLock.release()
    elif (sentinel == "UpdateLight"):
        lightEnabledLock.acquire()
        state = lightEnabled
        lightEnabledLock.release()
    elif (sentinel == "UpdateCPUTemp"):
        cpuEnabledLock.acquire()
        state = cpuEnabled
        cpuEnabledLock.release()
    elif (sentinel == "UpdateWatchedInterfaceIP"):
        interfaceIPEnabledLock.acquire()
        state = interfaceIPEnabled
        interfaceIPEnabledLock.release()
    elif (sentinel == "UpdatePublicIP"):
        publicIPEnabledLock.acquire()
        state = publicIPEnabled
        publicIPEnabledLock.release()
    elif (sentinel == "UpdateAccelerometer"):
        accelEnabledLock.acquire()
        state = accelEnabled
        accelEnabledLock.release()
    elif (sentinel == "UpdateButton"):
        buttonEnabledLock.acquire()
        state = buttonEnabled
        buttonEnabledLock.release()
    elif (sentinel == "SendValues"):
        sendEnabledLock.acquire()
        state = sendEnabled
        sendEnabledLock.release()
    else:
        state = False
    return state

# Method for the threads to check if their sentinels have changed
def SetSentinel(sentinel, state):
    global timeEnabled, ambientEnabled, lightEnabled, cpuEnabled, interfaceIPEnabled
    global publicIPEnabled, accelEnabled, buttonEnabled, sendEnabled
    # Check the thread's method name against the statements to
    # find their respective sentinel variables
    if sentinel == "UpdateDateTime":
        timeEnabledLock.acquire()
        timeEnabled = state
        timeEnabledLock.release()
    elif (sentinel == "UpdateAmbient"):
        ambientEnabledLock.acquire()
        ambientEnabled = state
        ambientEnabledLock.release()
    elif (sentinel == "UpdateLight"):
        lightEnabledLock.acquire()
        lightEnabled = state
        lightEnabledLock.release()
    elif (sentinel == "UpdateCPUTemp"):
        cpuEnabledLock.acquire()
        cpuEnabled = state
        cpuEnabledLock.release()
    elif (sentinel == "UpdateWatchedInterfaceIP"):
        interfaceIPEnabledLock.acquire()
        interfaceIPEnabled = state
        interfaceIPEnabledLock.release()
    elif (sentinel == "UpdatePublicIP"):
        publicIPEnabledLock.acquire()
        publicIPEnabled = state
        publicIPEnabledLock.release()
    elif (sentinel == "UpdateAccelerometer"):
        accelEnabledLock.acquire()
        accelEnabled = state
        accelEnabledLock.release()
    elif (sentinel == "UpdateButton"):
        buttonEnabledLock.acquire()
        buttonEnabled = state
        buttonEnabledLock.release()
    elif (sentinel == "SendValues"):
        sendEnabledLock.acquire()
        sendEnabled = state
        sendEnabledLock.release()


# Example IFTTT integration to call a trigger on their Maker Channel when
# a button is pressed
'''
def ButtonHandler():
    url = "https://maker.ifttt.com/trigger/" + iftttEvent + "/with/key/" + iftttKey
    # Make a POST request to the IFTTT maker channel URL using the event name
    # and API key provided in the config file, catching any failures
    try:
        r = requests.post(url, timeout=postTimeout)
        # print r.text #For debugging POST requests
    except:
        print "POST ERROR - Check connection and server"
'''

def ButtonHandler(pressed):
    global inMenu
    global currentMenu
    global menuElements
    global menuPosition
    inMenuLock.acquire()
    tempInMenu = inMenu
    inMenuLock.release()
    if (tempInMenu == False):
        print("Display Pressed " + str(pressed))
        if (pressed == 2):
            inMenuLock.acquire()
            inMenu = True
            inMenuLock.release()
            changeMenu("Top")
            menuElementsLock.acquire()
            menuElements = topMenuElements
            menuElementsLock.release()
            cursorToTop()
    else:
        print("Menu Pressed " + str(pressed))
        currentMenuLock.acquire()
        tempMenu = currentMenu
        currentMenuLock.release()
        menuElementsLock.acquire()
        tempElements = menuElements
        menuElementsLock.release()
        tempLength = len(tempElements)
        menuPositionLock.acquire()
        tempMenuPos = menuPosition
        menuPositionLock.release()
        if (pressed == 1):
            if (tempMenuPos == 0):
                menuPositionLock.acquire()
                menuPosition = tempLength - 1
                menuPositionLock.release()
            elif (tempMenuPos != 0):
                menuPositionLock.acquire()
                menuPosition = tempMenuPos - 1
                menuPositionLock.release()
        elif (pressed == 3):
            if (tempMenuPos == tempLength - 1):
                cursorToTop()
            elif (tempMenuPos != tempLength - 1):
                menuPositionLock.acquire()
                menuPosition = tempMenuPos + 1
                menuPositionLock.release()
        # If the middle button was pressed, check the menu it was in
        elif (pressed == 2):
            global postInterval, ambientInterval
            # If it was the top menu, which menu option was selected
            if (tempMenu == "Top"):
                # If Exit was selected, close the menu
                if (tempElements[tempMenuPos] == "Exit"):
                    closeMenu()
                # If General was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "General"):
                    changeMenu("General")
                    menuElementsLock.acquire()
                    menuElements = ["Back", "Watched Interface", "CPU Temp Interval", "Interface Interval",
                                    "Public Interval"]
                    menuElementsLock.release()
                    cursorToTop()
                # If UI was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "UI"):
                    changeMenu("UI")
                    menuElementsLock.acquire()
                    menuElements = ["Back", "Default Orientation", "Lock Orientation", "Refresh Interval",
                                    "Display Enabled", "Print Enabled"]
                    menuElementsLock.release()
                    cursorToTop()
                # If Requests was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "Requests"):
                    changeMenu("Requests")
                    menuElementsLock.acquire()
                    menuElements = ["Back", "POST Enabled", "POST Interval", "POST Timeout", "Server URL",
                                    "IFTTT Key", "IFTTT Event"]
                    menuElementsLock.release()
                    cursorToTop()
                # If Ambient was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "Ambient"):
                    changeMenu("Ambient")
                    menuElementsLock.acquire()
                    menuElements = ["Back", "Ambient Enabled", "Ambient Interval"]
                    menuElementsLock.release()
                    cursorToTop()
                # If Light was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "Light"):
                    changeMenu("Light")
                    menuElementsLock.acquire()
                    menuElements = ["Back", "Light Enabled", "Light Interval"]
                    menuElementsLock.release()
                    cursorToTop()
                # If Accelerometer was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "Accelerometer"):
                    changeMenu("Accelerometer")
                    menuElementsLock.acquire()
                    menuElements = ["Back", "Accel Enabled", "Accel Interval"]
                    menuElementsLock.release()
                    cursorToTop()
                # If System was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "System"):
                    changeMenu("System")
                    menuElementsLock.acquire()
                    menuElements = ["Back", "Shutdown", "Reboot", "Kill Program"]
                    menuElementsLock.release()
                    cursorToTop()
            # If we are in the general sub-menu already, which one of these options was selected
            elif (tempMenu == "General"):
                # If Back was selected, return to the Top menu
                if (tempElements[tempMenuPos] == "Back"):
                    changeMenu("Top")
                    menuElementsLock.acquire()
                    menuElements = topMenuElements
                    menuElementsLock.release()
                    cursorToTop()
                # If Watched Interface was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "Watched Interface"):
                    changeMenu("Watched Interface")
                    # Get the list of watchable interfaces before pulling up the menu
                    proc = subprocess.Popen(["ls", "-1", "/sys/class/net"], stdout=subprocess.PIPE)
                    (out, err) = proc.communicate()
                    interfaces = out.rstrip()
                    interfacesList = interfaces.split()
                    menuElementsLock.acquire()
                    menuElements = interfacesList
                    menuElementsLock.release()
                    cursorToTop()
                # If CPU Temp Interval was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "CPU Temp Interval"):
                    changeMenu("CPU Temp Interval")
                    # Prepare a list of possible quick options for the interval
                    menuElementsLock.acquire()
                    menuElements = [1, 2, 3, 4, 5, 10, 15, 20, 30, 60]
                    menuElementsLock.release()
                    cursorToTop()
                # If Interface Interval was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "Interface Interval"):
                    changeMenu("Interface Interval")
                    # Prepare a list of possible quick options for the interval
                    menuElementsLock.acquire()
                    menuElements = [1, 2, 3, 4, 5, 10, 15, 20, 30, 60]
                    menuElementsLock.release()
                    cursorToTop()
                # If Public Interval was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "Public Interval"):
                    changeMenu("Public Interval")
                    # Prepare a list of possible quick options for the interval
                    menuElementsLock.acquire()
                    menuElements = [10, 15, 20, 30, 60, 120, 240, 360, 480, 600]
                    menuElementsLock.release()
                    cursorToTop()
            # If an option was selected in the Watched Interface menu, update the config parser with the new value
            # as well as the global variable, no need to reboot the thread as it checks which interface each time
            elif (tempMenu == "Watched Interface"):
                global watchedInterface
                newInterface = tempElements[tempMenuPos]
                interfaceLock.acquire()
                watchedInterface = newInterface
                interfaceLock.release()
                parser.set('General', 'watchedinterface', newInterface)
                UpdateWatchedInterfaceIP()
                closeMenu()
            # If an option was selected in the following menus, update the config parser with the new value
            # to be written on close and reboot the respective monitoring thread with the new value
            elif (tempMenu == "CPU Temp Interval"):
                newTempInterval = tempElements[tempMenuPos]
                parser.set('General', 'cputempinterval', str(newTempInterval))
                rebootThread("CPUTempThread", newTempInterval, "UpdateCPUTemp")
                closeMenu()
            elif (tempMenu == "Interface Interval"):
                newInterfaceInterval = tempElements[tempMenuPos]
                parser.set('General', 'interfaceinterval', str(newInterfaceInterval))
                rebootThread("InterfaceIPThread", newInterfaceInterval, "UpdateWatchedInterfaceIP")
                closeMenu()
            elif (tempMenu == "Public Interval"):
                newPublicInterval = tempElements[tempMenuPos]
                parser.set('General', 'publicinterval', str(newPublicInterval))
                rebootThread("PublicIPThread", newPublicInterval, "UpdatePublicIP")
                closeMenu()
            # If we are in the UI sub-menu already, which one of these options was selected
            elif (tempMenu == "UI"):
                # If Back was selected, return to the Top menu
                if (tempElements[tempMenuPos] == "Back"):
                    changeMenu("Top")
                    menuElementsLock.acquire()
                    menuElements = topMenuElements
                    menuElementsLock.release()
                    cursorToTop()
                # If Default Orientation was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "Default Orientation"):
                    changeMenu("Default Orientation")
                    # Prepare a list of possible quick options for the orientation
                    menuElementsLock.acquire()
                    menuElements = ["0 = Landscape Left", "1 = Landscape Right",
                                    "2 = Portrait Up", "3 = Portrait Down"]
                    menuElementsLock.release()
                    cursorToTop()
                # If Lock Orientation was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "Lock Orientation"):
                    changeMenu("Lock Orientation")
                    # Can only be True or False
                    menuElementsLock.acquire()
                    menuElements = [True, False]
                    menuElementsLock.release()
                    cursorToTop()
                # If Refresh Interval was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "Refresh Interval"):
                    changeMenu("Refresh Interval")
                    # Prepare a list of possible quick options for the interval
                    menuElementsLock.acquire()
                    menuElements = [0.1, 0.25, 0.5, 0.75, 1, 1.5, 2, 2.5, 5, 10]
                    menuElementsLock.release()
                    cursorToTop()
                # If Display Enabled was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "Display Enabled"):
                    changeMenu("Display Enabled")
                    # Can only be True or False
                    menuElementsLock.acquire()
                    menuElements = [True, False]
                    menuElementsLock.release()
                    cursorToTop()
                # If Print Enabled was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "Print Enabled"):
                    changeMenu("Print Enabled")
                    # Can only be True or False
                    menuElementsLock.acquire()
                    menuElements = [True, False]
                    menuElementsLock.release()
                    cursorToTop()
            elif (tempMenu == "Default Orientation"):
                global defaultOrientation
                newOrientationString = tempElements[tempMenuPos]
                newOrientationSub = newOrientationString[0]
                set_config_value('defaultorientation', newOrientationSub)
                closeMenu()
            elif (tempMenu == "Lock Orientation"):
                global lockOrientation
                newLockOrientation = tempElements[tempMenuPos]
                set_config_value('lockorientation',newLockOrientation)
                closeMenu()
            elif (tempMenu == "Refresh Interval"):
                global sleepTime
                newRefreshInterval = tempElements[tempMenuPos]
                parser.set('UI', 'refreshinterval', str(newRefreshInterval))
                sleepTimeLock.acquire()
                sleepTime = newRefreshInterval
                sleepTimeLock.release()
                closeMenu()
            elif (tempMenu == "Display Enabled"):
                global displayEnabled
                newDisplayEnabled = tempElements[tempMenuPos]
                parser.set('UI', 'displayenabled', str(newDisplayEnabled))
                displayEnabledLock.acquire()
                displayEnabled = newDisplayEnabled
                displayEnabledLock.release()
                closeMenu()
            elif (tempMenu == "Print Enabled"):
                global printEnabled
                newPrintEnabled = tempElements[tempMenuPos]
                parser.set('UI', 'printenabled', str(newPrintEnabled))
                printEnabledLock.acquire()
                printEnabled = newPrintEnabled
                printEnabledLock.release()
                closeMenu()
            # If we are in the Requests sub-menu already, which one of these options was selected
            elif (tempMenu == "Requests"):
                # If Back was selected, return to the Top menu
                if (tempElements[tempMenuPos] == "Back"):
                    changeMenu("Top")
                    menuElementsLock.acquire()
                    menuElements = topMenuElements
                    menuElementsLock.release()
                    cursorToTop()
                # If POST Enabled was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "POST Enabled"):
                    changeMenu("POST Enabled")
                    # Can only be True or False
                    menuElementsLock.acquire()
                    menuElements = [True, False]
                    menuElementsLock.release()
                    cursorToTop()
                # If POST Interval was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "POST Interval"):
                    changeMenu("POST Interval")
                    # Prepare a list of possible quick options for the orientation
                    menuElementsLock.acquire()
                    menuElements = [1, 2, 3, 4, 5, 10, 15, 20, 30, 60]
                    menuElementsLock.release()
                    cursorToTop()
                # If POST Timeout was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "POST Timeout"):
                    changeMenu("POST Interval")
                    # Prepare a list of possible quick options for the orientation
                    menuElementsLock.acquire()
                    menuElements = [1, 2, 3, 4, 5, 10, 15, 20, 30, 60]
                    menuElementsLock.release()
                    cursorToTop()
            elif (tempMenu == "POST Enabled"):
                global sendEnabled
                newSendEnabled = tempElements[tempMenuPos]
                parser.set('Requests', 'sendenabled', str(newSendEnabled))
                sendEnabledLock.acquire()
                if (newSendEnabled != sendEnabled):
                    sendEnabled = newSendEnabled
                    sendEnabledLock.release()
                    if newSendEnabled == True:
                        rebootThread("SendThread", postInterval, "SendValues")
                elif (newSendEnabled == sendEnabled):
                    sendEnabledLock.release()
                closeMenu()
            elif (tempMenu == "POST Interval"):
                # global postInterval
                newPostInterval = tempElements[tempMenuPos]
                postInterval = newPostInterval
                parser.set('Requests', 'postinterval', str(newPostInterval))
                rebootThread("SendThread", newPostInterval, "SendValues")
                closeMenu()
            elif (tempMenu == "POST Timeout"):
                global postTimeout
                newPostTimeout = tempElements[tempMenuPos]
                parser.set('Requests', 'posttimeout', str(newPostTimeout))
                postTimeoutLock.acquire()
                postTimeout = newPostTimeout
                postTimeoutLock.release()
                closeMenu()
            # If we are in the Ambient sub-menu already, which one of these options was selected
            elif (tempMenu == "Ambient"):
                # If Back was selected, return to the Top menu
                if (tempElements[tempMenuPos] == "Back"):
                    changeMenu("Top")
                    menuElementsLock.acquire()
                    menuElements = topMenuElements
                    menuElementsLock.release()
                    cursorToTop()
                # If Ambient Enabled was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "Ambient Enabled"):
                    changeMenu("Ambient Enabled")
                    # Can only be True or False
                    menuElementsLock.acquire()
                    menuElements = [True, False]
                    menuElementsLock.release()
                    cursorToTop()
                # If Ambient Interval was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "Ambient Interval"):
                    changeMenu("Ambient Interval")
                    # Prepare a list of possible quick options for the orientation
                    menuElementsLock.acquire()
                    menuElements = [1, 2, 3, 4, 5, 10, 15, 20, 30, 60]
                    menuElementsLock.release()
                    cursorToTop()
            elif (tempMenu == "Ambient Enabled"):
                global ambientEnabled
                newAmbientEnabled = tempElements[tempMenuPos]
                parser.set('Ambient', 'ambientenabled', str(newAmbientEnabled))
                ambientEnabledLock.acquire()
                if (newAmbientEnabled != ambientEnabled):
                    ambientEnabled = newAmbientEnabled
                    ambientEnabledLock.release()
                    if newAmbientEnabled == True:
                        rebootThread("AmbientThread", ambientInterval, "UpdateAmbient")
                elif (newAmbientEnabled == ambientEnabled):
                    ambientEnabledLock.release()
                closeMenu()
            elif (tempMenu == "Ambient Interval"):
                # global ambientInterval
                newAmbientInterval = tempElements[tempMenuPos]
                ambientInterval = newAmbientInterval
                parser.set('Ambient', 'ambientinterval', str(newAmbientInterval))
                rebootThread("AmbientThread", newAmbientInterval, "UpdateAmbient")
                closeMenu()
            # If we are in the Light sub-menu already, which one of these options was selected
            elif (tempMenu == "Light"):
                # If Back was selected, return to the Top menu
                if (tempElements[tempMenuPos] == "Back"):
                    changeMenu("Top")
                    menuElementsLock.acquire()
                    menuElements = topMenuElements
                    menuElementsLock.release()
                    cursorToTop()
                # If Light Enabled was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "Light Enabled"):
                    changeMenu("Light Enabled")
                    # Can only be True or False
                    menuElementsLock.acquire()
                    menuElements = [True, False]
                    menuElementsLock.release()
                    cursorToTop()
                # If Light Interval was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "Light Interval"):
                    changeMenu("Light Interval")
                    # Prepare a list of possible quick options for the orientation
                    menuElementsLock.acquire()
                    menuElements = [1, 2, 3, 4, 5, 10, 15, 20, 30, 60]
                    menuElementsLock.release()
                    cursorToTop()
            elif (tempMenu == "Light Interval"):
                newLightInterval = tempElements[tempMenuPos]
                parser.set('Light', 'lightinterval', str(newLightInterval))
                rebootThread("LightThread", newLightInterval, "UpdateLight")
                closeMenu()
            elif (tempMenu == "Light Enabled"):
                global lightEnabled
                newlightEnabled = tempElements[tempMenuPos]
                parser.set('Light', 'lightenabled', str(newlightEnabled))
                lightEnabledLock.acquire()
                if (newlightEnabled != lightEnabled):
                    lightEnabled = newlightEnabled
                    lightEnabledLock.release()
                    if newlightEnabled == True:
                        rebootThread("LightThread", lightInterval, "UpdateLight")
                elif (newlightEnabled == lightEnabled):
                    lightEnabledLock.release()
                closeMenu()
            # If we are in the Accelerometer sub-menu already, which one of these options was selected
            elif (tempMenu == "Accelerometer"):
                # If Back was selected, return to the Top menu
                if (tempElements[tempMenuPos] == "Back"):
                    changeMenu("Top")
                    menuElementsLock.acquire()
                    menuElements = topMenuElements
                    menuElementsLock.release()
                    cursorToTop()
                # If Accel Enabled was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "Accel Enabled"):
                    changeMenu("Accel Enabled")
                    # Can only be True or False
                    menuElementsLock.acquire()
                    menuElements = [True, False]
                    menuElementsLock.release()
                    cursorToTop()
                # If Ambient Interval was selected, go into that sub-menu
                elif (tempElements[tempMenuPos] == "Accel Interval"):
                    changeMenu("Accel Interval")
                    # Prepare a list of possible quick options for the orientation
                    menuElementsLock.acquire()
                    menuElements = [1, 2, 3, 4, 5, 10, 15, 20, 30, 60]
                    menuElementsLock.release()
                    cursorToTop()
            elif (tempMenu == "Accel Enabled"):
                global accelEnabled
                newAccelEnabled = tempElements[tempMenuPos]
                parser.set('Accelerometer', 'accelenabled', str(newAccelEnabled))
                accelEnabledLock.acquire()
                if (newAccelEnabled != accelEnabled):
                    accelEnabled = newAccelEnabled
                    accelEnabledLock.release()
                    if newAccelEnabled == True:
                        rebootThread("AccelThread", accelInterval, "UpdateAccelerometer")
                elif (newAccelEnabled == accelEnabled):
                    accelEnabledLock.release()
                closeMenu()
            elif (tempMenu == "Accel Interval"):
                newAccelInterval = tempElements[tempMenuPos]
                parser.set('Accelerometer', 'accelinterval', str(newAccelInterval))
                rebootThread("AccelThread", newAccelInterval, "UpdateAccelerometer")
                closeMenu()
            # If we are in the System sub-menu already, which one of these options was selected
            elif (tempMenu == "System"):
                global killWatch
                # If Back was selected, return to the Top menu
                if (tempElements[tempMenuPos] == "Back"):
                    changeMenu("Top")
                    menuElementsLock.acquire()
                    menuElements = topMenuElements
                    menuElementsLock.release()
                    cursorToTop()
                # If Shutdown was selected, shutdown the Raspberry Pi
                elif (tempElements[tempMenuPos] == "Shutdown"):
                    kill_program()
                    # Gives the program 5 seconds to wrap things up before shutting down
                    os.system("sudo shutdown -h -t 5")
                # If Reboot was selected, reboot the Raspberry Pi
                elif (tempElements[tempMenuPos] == "Reboot"):
                    kill_program()
                    # Gives the program 5 seconds to wrap things up before rebooting
                    os.system("sudo shutdown -r -t 5")
                # If Kill Program was selected, terminate the program
                elif (tempElements[tempMenuPos] == "Kill Program"):
                    kill_program()


def kill_program():
    global killWatch
    killWatchLock.acquire()
    killWatch = True
    killWatchLock.release()


def shutdown_pi():
    kill_program()
    shutdown_helper = Process(target=shutdown_pi_helper)
    shutdown_helper.start()


def shutdown_pi_helper():
    os.system("sudo python shutdown.py -h -t 5")


def reboot_pi():
    kill_program()
    reboot_helper = Process(target=reboot_pi_helper)
    reboot_helper.start()


def reboot_pi_helper():
    os.system("sudo python shutdown.py -r -t 5")


# Changes the menu to the passed value
def changeMenu(newMenu):
    global currentMenu
    currentMenuLock.acquire()
    currentMenu = newMenu
    currentMenuLock.release()


# Close the LCD configuration menu
def closeMenu():
    global inMenu
    inMenuLock.acquire()
    inMenu = False
    inMenuLock.release()


# Brings the pointer arrow on the LCD menu to the top of whatever list is being shown
def cursorToTop():
    global menuPosition
    menuPositionLock.acquire()
    menuPosition = 0
    menuPositionLock.release()


def get_config_value(name):
    if (name == "defaultorientation"):
        defaultOrientationLock.acquire()
        _return_value = defaultOrientation
        defaultOrientationLock.release()
    elif (name == "lockorientation"):
        lockOrientationLock.acquire()
        _return_value = lockOrientation
        lockOrientationLock.release()
    else:
        _return_value = "ConfigNotFound"
    return str(_return_value)


def set_config_value(name, value):
    succeeded = False
    if (name == "defaultorientation"):
        global defaultOrientation
        defaultOrientationLock.acquire()
        try:
            defaultOrientation = int(value)
            parser.set('UI', 'defaultorientation', value)
            succeeded = True
        except:
            succeeded = False
        finally:
            defaultOrientationLock.release()
    elif (name == "lockorientation"):
        global lockOrientation
        lockOrientationLock.acquire()
        try:
            _lock_bool = bool_check(value)
            if _lock_bool == 1:
                lockOrientation = True
                parser.set('UI', 'lockorientation', 'True')
                succeeded = True
            elif _lock_bool == 0:
                lockOrientation = False
                parser.set('UI', 'lockorientation', 'False')
                succeeded = True
            elif _lock_bool == -1:
                succeeded = False
        except:
            succeeded = False
        finally:
            lockOrientationLock.release()
    return succeeded


def bool_check(value):
    if value in ['True', 'true', 'TRUE', 'T', 't', 'Y', 'y', '1']:
        return 1
    elif value in ['False', 'false', 'FALSE', 'F', 'f', 'N', 'n', '0']:
        return 0
    else:
        return -1

def get_all_config():
    _config_list = []
    _config_list.append({'name' : "defaultorientation", 'value' : get_config_value("defaultorientation")})
    _config_list.append({'name': "lockorientation", 'value': get_config_value("lockorientation")})
    return _config_list


def rebootThread(threadName, threadInterval, sentinelName):
    global threads
    if (CheckSentinel(sentinelName) == True):
        SetSentinel(sentinelName, False)
        for t in threads:
            if (t.getName() == threadName):
                t.join()
        SetSentinel(sentinelName, True)
        newThread = GeneralThread(len(threads) + 1, threadName, threadInterval, sentinelName)
        newThread.start()
        threads.append(newThread)


# Displays all the watched variables on the TFT LCD if enabled
def DisplayValues():
    disp.clear()
    # Checks if the orientation of the display should be locked
    # If so, force the default orientation from the config file
    lockOrientationLock.acquire()
    tempLockOrientation = lockOrientation
    lockOrientationLock.release()
    accelEnabledLock.acquire()
    tempAccelEnabled = accelEnabled
    accelEnabledLock.release()
    if (tempLockOrientation == False and tempAccelEnabled == True):
        orientation = GetMode()
    else:
        defaultOrientationLock.acquire()
        orientation = defaultOrientation
        defaultOrientationLock.release()
    # Depending on the orientation, prepare the display layout image
    if (orientation == 0):
        textDraw = Image.new('RGB', (160, 128))
        angle = 90
    elif (orientation == 1):
        textDraw = Image.new('RGB', (160, 128))
        angle = 270
    elif (orientation == 2):
        textDraw = Image.new('RGB', (128, 160))
        angle = 180
    elif (orientation == 3):
        textDraw = Image.new('RGB', (128, 160))
        angle = 0
    else:
        textDraw = Image.new('RGB', (128, 160))
        angle = 90

    # Draw the text objects for all the respective variables by getting
    # the latest values from their Get methods
    textDraw2 = ImageDraw.Draw(textDraw)

    inMenuLock.acquire()
    tempInMenu = inMenu
    inMenuLock.release()
    if (tempInMenu == False):
        textDraw2.text((0, 0), "HW: " + GetSerial(), font=font)
        rtcTime = GetDateTime()
        dat = "Date: " + str(rtcTime.date) + "/" + str(rtcTime.month) + "/" + str(
            rtcTime.year)  # convert to string and print it
        textDraw2.text((0, 12), dat, font=font)
        tmr = "Time: " + '{:02d}'.format(rtcTime.hour) + ":" + '{:02d}'.format(rtcTime.min) + ":" + '{:02d}'.format(
            rtcTime.sec)  # convert to string and print it
        textDraw2.text((0, 24), tmr, font=font)
        textDraw2.text((0, 36), "Light: " + str(GetLight()) + " lx", font=font)
        textDraw2.text((0, 48), "Temp: " + str(GetAmbientTemp()) + " C", font=font)
        textDraw2.text((0, 60), "Press: " + str(GetAmbientPressure()) + " kPa", font=font)
        textDraw2.text((0, 72), "CPU Temp: " + str(GetCPUTemp()) + " C", font=font)
        textDraw2.text((0, 84), "LAN IP: " + str(GetWatchedInterfaceIP()), font=font)
        textDraw2.text((0, 96), "WAN IP: " + str(GetPublicIP()), font=font)
        # textDraw2.text((0, 108), "Button Pressed: " + str(GetButton()), font=font)
        textDraw2.text((0, 108), "X: " + str(GetAccelX()) + " Y: " + str(GetAccelY()) + " Z: " + str(GetAccelZ()),
                       font=font)
    else:
        menuElementsLock.acquire()
        tempElements = menuElements
        menuElementsLock.release()
        for x in range(0,10):
            try:
                textDraw2.text((18, x*12), str(tempElements[x]), font=font)
            except IndexError:
                break
        menuPositionLock.acquire()
        tempMenuPos = menuPosition
        menuPositionLock.release()
        textDraw2.text((0, tempMenuPos*12), ">>", font=font)

    # Rotate the image to the set orientation and add it to the LCD
    textDraw3 = textDraw.rotate(angle)
    canvas = Image.new("RGB", (128, 160))
    canvas.paste(textDraw3, (0, 0))
    disp.display(canvas)

# Prints all the watched variables to the console if enabled
def PrintValues():
    options = {-1: "Not Ready",
               0: "Landscape Left",
               1: "Landscape Right",
               2: "Portrait Up",
               3: "Portrait Down"
               }
    # Get the current date and time and the latest update of all the watched
    # variables and print them to the console
    rtcTime = GetDateTime()
    print("HW: " + GetSerial())
    print("Date: " + str(rtcTime.date) + "/" + str(rtcTime.month) + "/" + str(
        rtcTime.year))  # convert to string and print it
    print("Time: " + '{:02d}'.format(rtcTime.hour) + ":" + '{:02d}'.format(rtcTime.min) + ":" + '{:02d}'.format(
        rtcTime.sec))
    print("Light: " + str(GetLight()) + " lx")
    print("Temp: " + str(GetAmbientTemp()) + " C")
    print("Pressure: " + str(GetAmbientPressure()) + " kPa")
    print("CPU Temp: " + str(GetCPUTemp()) + " C")
    print("LAN IP: " + str(GetWatchedInterfaceIP()))
    print("WAN IP: " + GetPublicIP())
    print("Mode: " + options[GetMode()])
    print("Button Pressed: " + str(GetButton()))
    print("--------------------")


# POST the variables in JSON format to the URL specified in the config file
def SendValues():
    rtcTime = GetDateTime()
    TS = "20" + '{:02d}'.format(rtcTime.year) + "-" + '{:02d}'.format(rtcTime.month) + "-" + '{:02d}'.format(
        rtcTime.date) + " " + '{:02d}'.format(rtcTime.hour) + ":" + '{:02d}'.format(
        rtcTime.min) + ":" + '{:02d}'.format(rtcTime.sec)
    # Prepare a JSON of the variables
    payload = {'HW': str(GetSerial()),
               'TS': TS,
               'IP': str(GetWatchedInterfaceIP()),
               'CPU': str(GetCPUTemp()),
               'LUX': str(GetLight()),
               'Temp': str(GetAmbientTemp()),
               'Press': str(GetAmbientPressure()),
               'X': str(old_div(GetAccelX(), 1000.0)),
               'Y': str(old_div(GetAccelY(), 1000.0)),
               'Z': str(old_div(GetAccelZ(), 1000.0))
               }
    # Attempt to POST the JSON to the given URL, catching any failures
    postTimeoutLock.acquire()
    tempTimeout = postTimeout
    postTimeoutLock.release()
    try:
        r = requests.post(serverURL, data=json.dumps(payload), timeout=tempTimeout)
        # print r.text #For debugging POST requests
    except:
        print("POST ERROR - Check connection and server")


# Method names for the threads to call to update their variables
methods = {"UpdateDateTime": UpdateDateTime,
           "UpdateAmbient": UpdateAmbient,
           "UpdateLight": UpdateLight,
           "UpdateCPUTemp": UpdateCPUTemp,
           "UpdateWatchedInterfaceIP": UpdateWatchedInterfaceIP,
           "UpdatePublicIP": UpdatePublicIP,
           "UpdateAccelerometer": UpdateAccelerometer,
           "UpdateButton": UpdateButton,
           "SendValues": SendValues,
           }


# Method to read the config file or set defaults if parameters missing
def Config():
    print("-------------------------")
    print("Configuring Settings")
    global parser
    parser = configparser.SafeConfigParser()
    # Read the config file if present
    parser.read('client.cfg')

    # The following similar blocks of code check every variable that should
    # be in the config file, setting the global variable for it if it exists
    # and setting it to default if it does not
    global defaultOrientation
    try:
        defaultOrientation = parser.getint('UI', 'defaultorientation')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('UI', 'defaultorientation', str(defaultOrientation))
        except(configparser.NoSectionError):
            parser.add_section('UI')
            parser.set('UI', 'defaultorientation', str(defaultOrientation))
    finally:
        print("Default Orientation: " + str(defaultOrientation))

    global lockOrientation
    try:
        lockOrientation = parser.getboolean('UI', 'lockorientation')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('UI', 'lockorientation', str(lockOrientation))
        except(configparser.NoSectionError):
            parser.add_section('UI')
            parser.set('UI', 'lockorientation', str(lockOrientation))
    finally:
        print("Lock Orientation: " + str(lockOrientation))

    global sleepTime
    try:
        sleepTime = parser.getfloat('UI', 'refreshinterval')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('UI', 'refreshinterval', str(sleepTime))
        except(configparser.NoSectionError):
            parser.add_section('UI')
            parser.set('UI', 'refreshinterval', str(sleepTime))
    finally:
        print("Refresh Interval: " + str(sleepTime))

    global watchedInterface
    try:
        watchedInterface = parser.get('General', 'watchedinterface')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('General', 'watchedinterface', watchedInterface)
        except(configparser.NoSectionError):
            parser.add_section('General')
            parser.set('General', 'watchedinterface', watchedInterface)
    finally:
        print("Watched Interface: " + watchedInterface)

    global sendEnabled
    try:
        sendEnabled = parser.getboolean('Requests', 'sendenabled')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('Requests', 'sendenabled', str(sendEnabled))
        except(configparser.NoSectionError):
            parser.add_section('Requests')
            parser.set('Requests', 'sendenabled', str(sendEnabled))
    finally:
        print("Send Enabled: " + str(sendEnabled))

    global postInterval
    try:
        postInterval = parser.getfloat('Requests', 'postinterval')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('Requests', 'postinterval', str(postInterval))
        except(configparser.NoSectionError):
            parser.add_section('Requests')
            parser.set('Requests', 'postinterval', str(postInterval))
    finally:
        print("POST Interval: " + str(postInterval))

    global postTimeout
    try:
        postTimeout = parser.getfloat('Requests', 'posttimeout')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('Requests', 'posttimeout', str(postTimeout))
        except(configparser.NoSectionError):
            parser.add_section('Requests')
            parser.set('Requests', 'posttimeout', str(postTimeout))
    finally:
        print("POST Timeout: " + str(postTimeout))

    global ambientEnabled
    try:
        ambientEnabled = parser.getboolean('Ambient', 'ambientenabled')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('Ambient', 'ambientenabled', str(ambientEnabled))
        except(configparser.NoSectionError):
            parser.add_section('Ambient')
            parser.set('Ambient', 'ambientenabled', str(ambientEnabled))
    finally:
        print("Ambient Enabled: " + str(ambientEnabled))

    global ambientInterval
    try:
        ambientInterval = parser.getfloat('Ambient', 'ambientinterval')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('Ambient', 'ambientinterval', str(ambientInterval))
        except(configparser.NoSectionError):
            parser.add_section('Ambient')
            parser.set('Ambient', 'ambientinterval', str(ambientInterval))
    finally:
        print("Ambient Interval: " + str(ambientInterval))

    global lightEnabled
    try:
        lightEnabled = parser.getboolean('Light', 'lightenabled')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('Light', 'lightenabled', str(lightEnabled))
        except(configparser.NoSectionError):
            parser.add_section('Light')
            parser.set('Light', 'lightenabled', str(lightEnabled))
    finally:
        print("Light Enabled: " + str(lightEnabled))

    global lightInterval
    try:
        lightInterval = parser.getfloat('Light', 'lightinterval')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('Light', 'lightinterval', str(lightInterval))
        except(configparser.NoSectionError):
            parser.add_section('Light')
            parser.set('Light', 'lightinterval', str(lightInterval))
    finally:
        print("Light Interval: " + str(lightInterval))

    global cpuTempInterval
    try:
        cpuTempInterval = parser.getfloat('General', 'cputempinterval')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('General', 'cputempinterval', str(cpuTempInterval))
        except(configparser.NoSectionError):
            parser.add_section('General')
            parser.set('General', 'cputempinterval', str(cpuTempInterval))
    finally:
        print("CPU Temp Interval: " + str(cpuTempInterval))

    global interfaceInterval
    try:
        interfaceInterval = parser.getfloat('General', 'interfaceinterval')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('General', 'interfaceinterval', str(interfaceInterval))
        except(configparser.NoSectionError):
            parser.add_section('General')
            parser.set('General', 'interfaceinterval', str(interfaceInterval))
    finally:
        print("Local IP Interval: " + str(interfaceInterval))

    global publicInterval
    try:
        publicInterval = parser.getfloat('General', 'publicinterval')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('General', 'publicinterval', str(publicInterval))
        except(configparser.NoSectionError):
            parser.add_section('General')
            parser.set('General', 'publicinterval', str(publicInterval))
    finally:
        print("Public IP Interval: " + str(publicInterval))

    global accelEnabled
    try:
        accelEnabled = parser.getboolean('Accelerometer', 'accelenabled')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('Accelerometer', 'accelenabled', str(accelEnabled))
        except(configparser.NoSectionError):
            parser.add_section('Accelerometer')
            parser.set('Accelerometer', 'accelenabled', str(accelEnabled))
    finally:
        print("Accel Enabled: " + str(accelEnabled))

    global accelInterval
    try:
        accelInterval = parser.getfloat('Accelerometer', 'accelinterval')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('Accelerometer', 'accelinterval', str(accelInterval))
        except(configparser.NoSectionError):
            parser.add_section('Accelerometer')
            parser.set('Accelerometer', 'accelinterval', str(accelInterval))
    finally:
        print("Accelerometer Interval: " + str(accelInterval))

    global displayEnabled
    try:
        displayEnabled = parser.getboolean('UI', 'displayenabled')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('UI', 'displayenabled', str(displayEnabled))
        except(configparser.NoSectionError):
            parser.add_section('UI')
            parser.set('UI', 'displayenabled', str(displayEnabled))
    finally:
        print("Display Enabled: " + str(displayEnabled))

    global printEnabled
    try:
        printEnabled = parser.getboolean('UI', 'printenabled')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('UI', 'printenabled', str(printEnabled))
        except(configparser.NoSectionError):
            parser.add_section('UI')
            parser.set('UI', 'printenabled', str(printEnabled))
    finally:
        print("Print Enabled: " + str(printEnabled))

    global serverURL
    try:
        serverURL = parser.get('Requests', 'serverurl')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('Requests', 'serverurl', serverURL)
        except(configparser.NoSectionError):
            parser.add_section('Requests')
            parser.set('Requests', 'serverurl', serverURL)
    finally:
        print("Server URL: " + serverURL)

    global iftttKey
    try:
        iftttKey = parser.get('Requests', 'iftttkey')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('Requests', 'iftttkey', iftttKey)
        except(configparser.NoSectionError):
            parser.add_section('Requests')
            parser.set('Requests', 'iftttkey', iftttKey)
    finally:
        print("IFTTT Key: " + iftttKey)

    global iftttEvent
    try:
        iftttEvent = parser.get('Requests', 'iftttevent')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        try:
            parser.set('Requests', 'iftttevent', iftttEvent)
        except(configparser.NoSectionError):
            parser.add_section('Requests')
            parser.set('Requests', 'iftttevent', iftttEvent)
    finally:
        print("IFTTT Event: " + iftttEvent)

    # Write the config file back to disk with the given values and
    # filling in any blanks with the defaults
    writeConfig()

    print("-------------------------")


# Writes any changes to the config file back to disk whenever changes are made
def writeConfig():
    with open('client.cfg', 'w') as configfile:
        parser.write(configfile)
        os.system("chmod 777 client.cfg")

# Main Method
def main():
    # CPU serial shouldn't change so it is only updated once
    UpdateSerial()

    # Create threads and start them to monitor the various sensors and
    # IP variables at their given intervals, 1 second interval for time/buttons
    rebootThread("TimeThread", 1, "UpdateDateTime")
    rebootThread("AmbientThread", ambientInterval, "UpdateAmbient")
    rebootThread("LightThread", lightInterval, "UpdateLight")
    rebootThread("CPUTempThread", cpuTempInterval, "UpdateCPUTemp")
    rebootThread("InterfaceIPThread", interfaceInterval, "UpdateWatchedInterfaceIP")
    rebootThread("PublicIPThread", publicInterval, "UpdatePublicIP")
    rebootThread("AccelThread", accelInterval, "UpdateAccelerometer")
    rebootThread("SendThread", postInterval, "SendValues")

    flaskThread = FlaskThread()
    flaskThread.start()

    # Set up the GPIO for the touch buttons and LED
    GPIO.setup(CAP_PIN, GPIO.IN)
    GPIO.setup(LED_PIN, GPIO.OUT)
    GPIO.add_event_detect(CAP_PIN, GPIO.FALLING)
    GPIO.add_event_callback(CAP_PIN, ButtonEventHandler)

    # Enable interrupts on the buttons
    CapTouch.clearInterrupt()
    CapTouch.enableInterrupt(0, 0, 0x07)

    killWatchLock.acquire()
    tempKillWatch = killWatch
    killWatchLock.release()

    # Loop the display and/or printing of variables if desired, waiting between
    # calls for the set or default refresh interval
    while tempKillWatch == False:
        printEnabledLock.acquire()
        tempPrintEnabled = printEnabled
        printEnabledLock.release()
        if tempPrintEnabled:
            PrintValues()

        displayEnabledLock.acquire()
        tempDisplayEnabled = displayEnabled
        displayEnabledLock.release()
        if tempDisplayEnabled:
            DisplayValues()

        sleepTimeLock.acquire()
        tempSleepTime = sleepTime
        sleepTimeLock.release()
        time.sleep(tempSleepTime)

        killWatchLock.acquire()
        tempKillWatch = killWatch
        killWatchLock.release()


# Assuming this program is run itself, execute normally
if __name__ == "__main__":
    # Initialize variables once by reading or creating the config file
    Config()
    # Run the main method, halting on keyboard interrupt if run from console
    try:
        main()
    except KeyboardInterrupt:
        print("...Quitting ...")
    # Tell all threads to stop if the main program stops by setting their
    # respective repeat sentinels to False
    finally:
        kill_flask()

        GPIO.cleanup()

        writeConfig()

        timeEnabledLock.acquire()
        timeEnabled = False
        timeEnabledLock.release()

        ambientEnabledLock.acquire()
        ambientEnabled = False
        ambientEnabledLock.release()

        lightEnabledLock.acquire()
        lightEnabled = False
        lightEnabledLock.release()

        accelEnabledLock.acquire()
        accelEnabled = False
        accelEnabledLock.release()

        cpuEnabledLock.acquire()
        cpuEnabled = False
        cpuEnabledLock.release()

        interfaceIPEnabledLock.acquire()
        interfaceIPEnabled = False
        interfaceIPEnabledLock.release()

        publicIPEnabledLock.acquire()
        publicIPEnabled = False
        publicIPEnabledLock.release()

        buttonEnabledLock.acquire()
        buttonEnabled = False
        buttonEnabledLock.release()

        sendEnabledLock.acquire()
        sendEnabled = False
        sendEnabledLock.release()
