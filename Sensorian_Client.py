#!/usr/bin/python
from __future__ import print_function
from __future__ import division
from future import standard_library
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

standard_library.install_aliases()

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
INT_PIN = 11  # Ambient Light Sensor Interrupt - BCM 17
LED_PIN = 12  # LED - BCM 18
CAP_PIN = 13  # Capacitive Touch Button Interrupt - BCM 27
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
interfaceIntervalLock = threading.Lock()
publicIntervalLock = threading.Lock()
postIntervalLock = threading.Lock()
serverURLLock = threading.Lock()
iftttKeyLock = threading.Lock()
iftttEventLock = threading.Lock()
ambientIntervalLock = threading.Lock()
lightIntervalLock = threading.Lock()
accelIntervalLock = threading.Lock()
cpuTempIntervalLock = threading.Lock()

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
        config_list = get_all_config()
        # for variable in config_list
        return {'variables': config_list}
        # return {'variables': [marshal(variable, config_fields) for variable in _config_list]}


class ConfigAPI(Resource):
    decorators = [auth.login_required]

    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument('name', type=str, location='json')
        self.reqparse.add_argument('value', type=str, location='json')
        super(ConfigAPI, self).__init__()

    def get(self, name):
        config_temp = get_config_value(name)
        if config_temp != "ConfigNotFound":
            return {'name': name, 'value': config_temp}
        else:
            abort(404)

    def put(self, name):
        config_temp = get_config_value(name)
        if config_temp != "ConfigNotFound":
            args = self.reqparse.parse_args()
            if args['value'] is not None:
                set_temp = set_config_value(name, args['value'])
                if set_temp:
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
def update_serial():
    # Extract serial from cpuinfo file
    global cpuSerial
    temp_serial = "0000000000000000"
    # Get serial from the file, if fails, return error serial
    try:
        f = open('/proc/cpuinfo', 'r')
        try:
            for line in f:
                if line[0:6] == 'Serial':
                    temp_serial = line[10:26]
        finally:
            f.close()
    except (IOError, OSError):
        temp_serial = "ERROR000000000"
    # Update the serial global variable when safe
    finally:
        serialLock.acquire()
        cpuSerial = temp_serial
        serialLock.release()


# Get the most recent update of the serial number when safe
def get_serial():
    serialLock.acquire()
    temp_serial = cpuSerial
    serialLock.release()
    return temp_serial


# General thread class to repeatedly update a variable at a set interval
class GeneralThread(threading.Thread):
    # Initializes a thread upon creation
    # Takes an artbitrary ID and name of thread, an interval float how often
    # to update the variable, and the method name to call to update it
    def __init__(self, thread_id, name, interval, method):
        threading.Thread.__init__(self)
        self.threadID = thread_id
        self.name = name
        if interval < 1:
            self.interval = 1
        else:
            self.interval = interval
        self.method = method
        self.repeat = check_sentinel(self.method)
        self.slept = 0
        self.toSleep = 0

    def run(self):
        # Thread loops as long as the sentinel remains True
        while self.repeat:
            methods[self.method]()
            self.slept = 0
            # Keep sleeping until it's time to update again
            while self.slept < self.interval:
                # Check the global sentinel for this thread every second at most
                self.repeat = check_sentinel(self.method)
                # If the sentinel changed to false this second, kill the thread
                if not self.repeat:
                    print("Killing " + self.name)
                    break
                # If it did not, sleep for another second unless less than a
                # second needs to pass to reach the end of the current loop
                if self.interval - self.slept < 1:
                    self.toSleep = self.interval - self.slept
                else:
                    self.toSleep = 1
                time.sleep(self.toSleep)
                self.slept += self.toSleep


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
def update_light():
    global light
    temp_light = -1
    I2CLock.acquire()
    # Try to initialize and update the light value
    # Sometimes it excepts, so catch it if it does
    try:
        ambient_light = LuxSens.APDS9300()
        channel1 = ambient_light.readChannel(1)
        channel2 = ambient_light.readChannel(0)
        temp_light = ambient_light.getLuxLevel(channel1, channel2)
    except:
        print("EXCEPTION IN LIGHT UPDATE")
    I2CLock.release()
    # Update the global light level when safe
    lightLock.acquire()
    light = temp_light
    lightLock.release()


# Get the most recent update of the light level when safe
def get_light():
    lightLock.acquire()
    try:
        temp_light = light
    finally:
        lightLock.release()
    return temp_light


# Get the most recent update of the ambient temperature when safe
def get_ambient_temp():
    ambientTempLock.acquire()
    return_temp = ambientTemp
    ambientTempLock.release()
    return return_temp


# Get the most recent update of the ambient pressure when safe
def get_ambient_pressure():
    ambientPressureLock.acquire()
    return_press = old_div(float(ambientPressure), 1000)
    ambientPressureLock.release()
    return return_press


# Update the various barometer/altimeter sensor variables
def update_ambient():
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
    temp_enabled = pressureEnabled
    pressureEnabledLock.release()
    # If pressure is needed, update the global variable when safe
    if temp_enabled:
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
    temp_enabled = pressureEnabled
    altitudeEnabledLock.release()
    if (temp_enabled):
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
def update_date_time():
    global currentDateTime
    I2CLock.acquire()
    temp_date_time = RTC.GetTime()
    I2CLock.release()
    rtcLock.acquire()
    currentDateTime = temp_date_time
    rtcLock.release()


# Get the most recent date and time when safe
def get_date_time():
    rtcLock.acquire()
    temp_date_time = currentDateTime
    rtcLock.release()
    return temp_date_time


# Update the global variable of the CPU temperature
def update_cpu_temp():
    # Read the CPU temperature from the system file
    global cpuTemp
    temp_path = '/sys/class/thermal/thermal_zone0/temp'
    temp_file = open(temp_path)
    cpu = temp_file.read()
    temp_file.close()
    temp = (old_div(float(cpu), 1000))
    # Update the global variable when safe
    cpuTempLock.acquire()
    cpuTemp = temp
    cpuTempLock.release()


# Get the latest update of the CPU temperature when safe
def get_cpu_temp():
    cpuTempLock.acquire()
    temp = cpuTemp
    cpuTempLock.release()
    return temp


# Update the global variable for the IP of the primary interface
def update_watched_interface_ip():
    global interfaceIP
    interfaceLock.acquire()
    temp_interface = watchedInterface
    interfaceLock.release()
    ipaddr = get_interface_ip(temp_interface)
    interfaceIPLock.acquire()
    interfaceIP = ipaddr
    interfaceIPLock.release()


# Get the latest IP of the primary interface when safe
def get_watched_interface_ip():
    interfaceIPLock.acquire()
    temp_ip = interfaceIP
    interfaceIPLock.release()
    return temp_ip


# Get the IP of the passed interface
def get_interface_ip(interface):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Try to get the IP of the passed interface
    try:
        ipaddr = socket.inet_ntoa(fcntl.ioctl(
            s.fileno(),
            0x8915,  # SIOCGIFADDR
            struct.pack('256s', interface[:15])
        )[20:24])
    # If it fails, return localhost IP
    except:
        ipaddr = "127.0.0.1"
    return ipaddr


# Update the global variable for current public IP from the icanhazip site
# Don't update too frequently, that's not cool
def update_public_ip():
    global publicIP
    # Initiate a subprocess to run a curl request for the public IP
    proc = subprocess.Popen(["curl", "-s", "-4", "icanhazip.com"], stdout=subprocess.PIPE)
    (out, err) = proc.communicate()
    # Store the response of the request when safe
    publicIPLock.acquire()
    publicIP = out.rstrip()
    publicIPLock.release()


# Get the latest update of the public IP address
def get_public_ip():
    publicIPLock.acquire()
    temp_ip = publicIP
    publicIPLock.release()
    return temp_ip


# Update all accelerometer related global variables when safe
def update_accelerometer():
    global mode
    global modeprevious
    global accelX
    global accelY
    global accelZ
    I2CLock.acquire()
    # If the accelerometer is ready, read the orientation and forces
    if imuSensor.readStatusReg() & 0x80:
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
        if mode != modeprevious:
            # Alert change in orientation if required
            # print "Changed orientation"
            modeprevious = get_mode()
    else:
        I2CLock.release()


# Get the latest update of the orientation from the global when safe
def get_mode():
    modeLock.acquire()
    temp_mode = mode
    modeLock.release()
    return temp_mode


# Get the latest update of the X acceleration when safe
def get_accel_x():
    accelXLock.acquire()
    x = accelX
    accelXLock.release()
    return x


# Get the latest update of the Y acceleration when safe
def get_accel_y():
    accelYLock.acquire()
    y = accelY
    accelYLock.release()
    return y


# Get the latest update of the Z acceleration when safe
def get_accel_z():
    accelZLock.acquire()
    z = accelZ
    accelZLock.release()
    return z


# Update the latest button press to the global variable
def update_button():
    print("You Shouldn't Be Here...")


# Update the button pressed when interrupted
def button_event_handler():
    GPIO.output(LED_PIN, True)
    global button
    I2CLock.acquire()
    temp_new_button = CapTouch.readPressedButton()
    I2CLock.release()
    buttonLock.acquire()
    button = temp_new_button
    buttonLock.release()
    while temp_new_button == 0:
        I2CLock.acquire()
        temp_new_button = CapTouch.readPressedButton()
        I2CLock.release()
    button_handler(temp_new_button)
    GPIO.output(LED_PIN, False)


# Get the latest update of the most recent button press
def get_button():
    buttonLock.acquire()
    temp_button = button
    buttonLock.release()
    return temp_button


# Method for the threads to check if their sentinels have changed
def check_sentinel(sentinel):
    # Check the thread's method name against the statements to
    # find their respective sentinel variables
    if sentinel == "UpdateDateTime":
        timeEnabledLock.acquire()
        state = timeEnabled
        timeEnabledLock.release()
    elif sentinel == "UpdateAmbient":
        ambientEnabledLock.acquire()
        state = ambientEnabled
        ambientEnabledLock.release()
    elif sentinel == "UpdateLight":
        lightEnabledLock.acquire()
        state = lightEnabled
        lightEnabledLock.release()
    elif sentinel == "UpdateCPUTemp":
        cpuEnabledLock.acquire()
        state = cpuEnabled
        cpuEnabledLock.release()
    elif sentinel == "UpdateWatchedInterfaceIP":
        interfaceIPEnabledLock.acquire()
        state = interfaceIPEnabled
        interfaceIPEnabledLock.release()
    elif sentinel == "UpdatePublicIP":
        publicIPEnabledLock.acquire()
        state = publicIPEnabled
        publicIPEnabledLock.release()
    elif sentinel == "UpdateAccelerometer":
        accelEnabledLock.acquire()
        state = accelEnabled
        accelEnabledLock.release()
    elif sentinel == "UpdateButton":
        buttonEnabledLock.acquire()
        state = buttonEnabled
        buttonEnabledLock.release()
    elif sentinel == "SendValues":
        sendEnabledLock.acquire()
        state = sendEnabled
        sendEnabledLock.release()
    else:
        state = False
    return state


# Method for the threads to check if their sentinels have changed
def set_sentinel(sentinel, state):
    global timeEnabled, ambientEnabled, lightEnabled, cpuEnabled, interfaceIPEnabled
    global publicIPEnabled, accelEnabled, buttonEnabled, sendEnabled
    # Check the thread's method name against the statements to
    # find their respective sentinel variables
    if sentinel == "UpdateDateTime":
        timeEnabledLock.acquire()
        timeEnabled = state
        timeEnabledLock.release()
    elif sentinel == "UpdateAmbient":
        ambientEnabledLock.acquire()
        ambientEnabled = state
        ambientEnabledLock.release()
    elif sentinel == "UpdateLight":
        lightEnabledLock.acquire()
        lightEnabled = state
        lightEnabledLock.release()
    elif sentinel == "UpdateCPUTemp":
        cpuEnabledLock.acquire()
        cpuEnabled = state
        cpuEnabledLock.release()
    elif sentinel == "UpdateWatchedInterfaceIP":
        interfaceIPEnabledLock.acquire()
        interfaceIPEnabled = state
        interfaceIPEnabledLock.release()
    elif sentinel == "UpdatePublicIP":
        publicIPEnabledLock.acquire()
        publicIPEnabled = state
        publicIPEnabledLock.release()
    elif sentinel == "UpdateAccelerometer":
        accelEnabledLock.acquire()
        accelEnabled = state
        accelEnabledLock.release()
    elif sentinel == "UpdateButton":
        buttonEnabledLock.acquire()
        buttonEnabled = state
        buttonEnabledLock.release()
    elif sentinel == "SendValues":
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


def button_handler(pressed):
    global inMenu
    global currentMenu
    global menuElements
    global menuPosition
    inMenuLock.acquire()
    temp_in_menu = inMenu
    inMenuLock.release()
    if not temp_in_menu:
        print("Display Pressed " + str(pressed))
        if pressed == 2:
            inMenuLock.acquire()
            inMenu = True
            inMenuLock.release()
            change_menu("Top")
            menuElementsLock.acquire()
            menuElements = topMenuElements
            menuElementsLock.release()
            cursor_to_top()
    else:
        print("Menu Pressed " + str(pressed))
        currentMenuLock.acquire()
        temp_menu = currentMenu
        currentMenuLock.release()
        menuElementsLock.acquire()
        temp_elements = menuElements
        menuElementsLock.release()
        temp_length = len(temp_elements)
        menuPositionLock.acquire()
        temp_menu_pos = menuPosition
        menuPositionLock.release()
        if pressed == 1:
            if temp_menu_pos == 0:
                menuPositionLock.acquire()
                menuPosition = temp_length - 1
                menuPositionLock.release()
            elif temp_menu_pos != 0:
                menuPositionLock.acquire()
                menuPosition = temp_menu_pos - 1
                menuPositionLock.release()
        elif pressed == 3:
            if temp_menu_pos == temp_length - 1:
                cursor_to_top()
            elif temp_menu_pos != temp_length - 1:
                menuPositionLock.acquire()
                menuPosition = temp_menu_pos + 1
                menuPositionLock.release()
        # If the middle button was pressed, check the menu it was in
        elif pressed == 2:
            global postInterval, ambientInterval
            # If it was the top menu, which menu option was selected
            if temp_menu == "Top":
                # If Exit was selected, close the menu
                if temp_elements[temp_menu_pos] == "Exit":
                    close_menu()
                # If General was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "General":
                    change_menu("General")
                    menuElementsLock.acquire()
                    menuElements = ["Back", "Watched Interface", "CPU Temp Interval", "Interface Interval",
                                    "Public Interval"]
                    menuElementsLock.release()
                    cursor_to_top()
                # If UI was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "UI":
                    change_menu("UI")
                    menuElementsLock.acquire()
                    menuElements = ["Back", "Default Orientation", "Lock Orientation", "Refresh Interval",
                                    "Display Enabled", "Print Enabled"]
                    menuElementsLock.release()
                    cursor_to_top()
                # If Requests was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "Requests":
                    change_menu("Requests")
                    menuElementsLock.acquire()
                    menuElements = ["Back", "POST Enabled", "POST Interval", "POST Timeout", "Server URL",
                                    "IFTTT Key", "IFTTT Event"]
                    menuElementsLock.release()
                    cursor_to_top()
                # If Ambient was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "Ambient":
                    change_menu("Ambient")
                    menuElementsLock.acquire()
                    menuElements = ["Back", "Ambient Enabled", "Ambient Interval"]
                    menuElementsLock.release()
                    cursor_to_top()
                # If Light was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "Light":
                    change_menu("Light")
                    menuElementsLock.acquire()
                    menuElements = ["Back", "Light Enabled", "Light Interval"]
                    menuElementsLock.release()
                    cursor_to_top()
                # If Accelerometer was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "Accelerometer":
                    change_menu("Accelerometer")
                    menuElementsLock.acquire()
                    menuElements = ["Back", "Accel Enabled", "Accel Interval"]
                    menuElementsLock.release()
                    cursor_to_top()
                # If System was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "System":
                    change_menu("System")
                    menuElementsLock.acquire()
                    menuElements = ["Back", "Shutdown", "Reboot", "Kill Program"]
                    menuElementsLock.release()
                    cursor_to_top()
            # If we are in the general sub-menu already, which one of these options was selected
            elif temp_menu == "General":
                # If Back was selected, return to the Top menu
                if temp_elements[temp_menu_pos] == "Back":
                    change_menu("Top")
                    menuElementsLock.acquire()
                    menuElements = topMenuElements
                    menuElementsLock.release()
                    cursor_to_top()
                # If Watched Interface was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "Watched Interface":
                    change_menu("Watched Interface")
                    # Get the list of watchable interfaces before pulling up the menu
                    proc = subprocess.Popen(["ls", "-1", "/sys/class/net"], stdout=subprocess.PIPE)
                    (out, err) = proc.communicate()
                    interfaces = out.rstrip()
                    interfaces_list = interfaces.split()
                    menuElementsLock.acquire()
                    menuElements = interfaces_list
                    menuElementsLock.release()
                    cursor_to_top()
                # If CPU Temp Interval was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "CPU Temp Interval":
                    change_menu("CPU Temp Interval")
                    # Prepare a list of possible quick options for the interval
                    menuElementsLock.acquire()
                    menuElements = [1, 2, 3, 4, 5, 10, 15, 20, 30, 60]
                    menuElementsLock.release()
                    cursor_to_top()
                # If Interface Interval was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "Interface Interval":
                    change_menu("Interface Interval")
                    # Prepare a list of possible quick options for the interval
                    menuElementsLock.acquire()
                    menuElements = [1, 2, 3, 4, 5, 10, 15, 20, 30, 60]
                    menuElementsLock.release()
                    cursor_to_top()
                # If Public Interval was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "Public Interval":
                    change_menu("Public Interval")
                    # Prepare a list of possible quick options for the interval
                    menuElementsLock.acquire()
                    menuElements = [10, 15, 20, 30, 60, 120, 240, 360, 480, 600]
                    menuElementsLock.release()
                    cursor_to_top()
            # If an option was selected in the Watched Interface menu, update the config parser with the new value
            # as well as the global variable, no need to reboot the thread as it checks which interface each time
            elif temp_menu == "Watched Interface":
                global watchedInterface
                new_interface = temp_elements[temp_menu_pos]
                interfaceLock.acquire()
                watchedInterface = new_interface
                interfaceLock.release()
                parser.set('General', 'watchedinterface', new_interface)
                update_watched_interface_ip()
                close_menu()
            # If an option was selected in the following menus, update the config parser with the new value
            # to be written on close and reboot the respective monitoring thread with the new value
            elif temp_menu == "CPU Temp Interval":
                new_temp_interval = temp_elements[temp_menu_pos]
                parser.set('General', 'cputempinterval', str(new_temp_interval))
                reboot_thread("CPUTempThread", new_temp_interval, "UpdateCPUTemp")
                close_menu()
            elif temp_menu == "Interface Interval":
                new_interface_interval = temp_elements[temp_menu_pos]
                parser.set('General', 'interfaceinterval', str(new_interface_interval))
                reboot_thread("InterfaceIPThread", new_interface_interval, "UpdateWatchedInterfaceIP")
                close_menu()
            elif temp_menu == "Public Interval":
                new_public_interval = temp_elements[temp_menu_pos]
                parser.set('General', 'publicinterval', str(new_public_interval))
                reboot_thread("PublicIPThread", new_public_interval, "UpdatePublicIP")
                close_menu()
            # If we are in the UI sub-menu already, which one of these options was selected
            elif temp_menu == "UI":
                # If Back was selected, return to the Top menu
                if temp_elements[temp_menu_pos] == "Back":
                    change_menu("Top")
                    menuElementsLock.acquire()
                    menuElements = topMenuElements
                    menuElementsLock.release()
                    cursor_to_top()
                # If Default Orientation was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "Default Orientation":
                    change_menu("Default Orientation")
                    # Prepare a list of possible quick options for the orientation
                    menuElementsLock.acquire()
                    menuElements = ["0 = Landscape Left", "1 = Landscape Right",
                                    "2 = Portrait Up", "3 = Portrait Down"]
                    menuElementsLock.release()
                    cursor_to_top()
                # If Lock Orientation was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "Lock Orientation":
                    change_menu("Lock Orientation")
                    # Can only be True or False
                    menuElementsLock.acquire()
                    menuElements = [True, False]
                    menuElementsLock.release()
                    cursor_to_top()
                # If Refresh Interval was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "Refresh Interval":
                    change_menu("Refresh Interval")
                    # Prepare a list of possible quick options for the interval
                    menuElementsLock.acquire()
                    menuElements = [0.1, 0.25, 0.5, 0.75, 1, 1.5, 2, 2.5, 5, 10]
                    menuElementsLock.release()
                    cursor_to_top()
                # If Display Enabled was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "Display Enabled":
                    change_menu("Display Enabled")
                    # Can only be True or False
                    menuElementsLock.acquire()
                    menuElements = [True, False]
                    menuElementsLock.release()
                    cursor_to_top()
                # If Print Enabled was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "Print Enabled":
                    change_menu("Print Enabled")
                    # Can only be True or False
                    menuElementsLock.acquire()
                    menuElements = [True, False]
                    menuElementsLock.release()
                    cursor_to_top()
            elif temp_menu == "Default Orientation":
                global defaultOrientation
                new_orientation_string = temp_elements[temp_menu_pos]
                new_orientation_sub = new_orientation_string[0]
                set_config_value('defaultorientation', new_orientation_sub)
                close_menu()
            elif temp_menu == "Lock Orientation":
                global lockOrientation
                new_lock_orientation = temp_elements[temp_menu_pos]
                set_config_value('lockorientation', new_lock_orientation)
                close_menu()
            elif temp_menu == "Refresh Interval":
                global sleepTime
                new_refresh_interval = temp_elements[temp_menu_pos]
                parser.set('UI', 'refreshinterval', str(new_refresh_interval))
                sleepTimeLock.acquire()
                sleepTime = new_refresh_interval
                sleepTimeLock.release()
                close_menu()
            elif temp_menu == "Display Enabled":
                global displayEnabled
                new_display_enabled = temp_elements[temp_menu_pos]
                parser.set('UI', 'displayenabled', str(new_display_enabled))
                displayEnabledLock.acquire()
                displayEnabled = new_display_enabled
                displayEnabledLock.release()
                close_menu()
            elif temp_menu == "Print Enabled":
                global printEnabled
                new_print_enabled = temp_elements[temp_menu_pos]
                parser.set('UI', 'printenabled', str(new_print_enabled))
                printEnabledLock.acquire()
                printEnabled = new_print_enabled
                printEnabledLock.release()
                close_menu()
            # If we are in the Requests sub-menu already, which one of these options was selected
            elif temp_menu == "Requests":
                # If Back was selected, return to the Top menu
                if temp_elements[temp_menu_pos] == "Back":
                    change_menu("Top")
                    menuElementsLock.acquire()
                    menuElements = topMenuElements
                    menuElementsLock.release()
                    cursor_to_top()
                # If POST Enabled was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "POST Enabled":
                    change_menu("POST Enabled")
                    # Can only be True or False
                    menuElementsLock.acquire()
                    menuElements = [True, False]
                    menuElementsLock.release()
                    cursor_to_top()
                # If POST Interval was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "POST Interval":
                    change_menu("POST Interval")
                    # Prepare a list of possible quick options for the orientation
                    menuElementsLock.acquire()
                    menuElements = [1, 2, 3, 4, 5, 10, 15, 20, 30, 60]
                    menuElementsLock.release()
                    cursor_to_top()
                # If POST Timeout was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "POST Timeout":
                    change_menu("POST Interval")
                    # Prepare a list of possible quick options for the orientation
                    menuElementsLock.acquire()
                    menuElements = [1, 2, 3, 4, 5, 10, 15, 20, 30, 60]
                    menuElementsLock.release()
                    cursor_to_top()
            elif temp_menu == "POST Enabled":
                global sendEnabled
                new_send_enabled = temp_elements[temp_menu_pos]
                parser.set('Requests', 'sendenabled', str(new_send_enabled))
                sendEnabledLock.acquire()
                if new_send_enabled != sendEnabled:
                    sendEnabled = new_send_enabled
                    sendEnabledLock.release()
                    if new_send_enabled:
                        reboot_thread("SendThread", postInterval, "SendValues")
                elif new_send_enabled == sendEnabled:
                    sendEnabledLock.release()
                close_menu()
            elif temp_menu == "POST Interval":
                # global postInterval
                new_post_interval = temp_elements[temp_menu_pos]
                postInterval = new_post_interval
                parser.set('Requests', 'postinterval', str(new_post_interval))
                reboot_thread("SendThread", new_post_interval, "SendValues")
                close_menu()
            elif temp_menu == "POST Timeout":
                global postTimeout
                new_post_timeout = temp_elements[temp_menu_pos]
                parser.set('Requests', 'posttimeout', str(new_post_timeout))
                postTimeoutLock.acquire()
                postTimeout = new_post_timeout
                postTimeoutLock.release()
                close_menu()
            # If we are in the Ambient sub-menu already, which one of these options was selected
            elif temp_menu == "Ambient":
                # If Back was selected, return to the Top menu
                if temp_elements[temp_menu_pos] == "Back":
                    change_menu("Top")
                    menuElementsLock.acquire()
                    menuElements = topMenuElements
                    menuElementsLock.release()
                    cursor_to_top()
                # If Ambient Enabled was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "Ambient Enabled":
                    change_menu("Ambient Enabled")
                    # Can only be True or False
                    menuElementsLock.acquire()
                    menuElements = [True, False]
                    menuElementsLock.release()
                    cursor_to_top()
                # If Ambient Interval was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "Ambient Interval":
                    change_menu("Ambient Interval")
                    # Prepare a list of possible quick options for the orientation
                    menuElementsLock.acquire()
                    menuElements = [1, 2, 3, 4, 5, 10, 15, 20, 30, 60]
                    menuElementsLock.release()
                    cursor_to_top()
            elif temp_menu == "Ambient Enabled":
                global ambientEnabled
                new_ambient_enabled = temp_elements[temp_menu_pos]
                parser.set('Ambient', 'ambientenabled', str(new_ambient_enabled))
                ambientEnabledLock.acquire()
                if new_ambient_enabled != ambientEnabled:
                    ambientEnabled = new_ambient_enabled
                    ambientEnabledLock.release()
                    if new_ambient_enabled:
                        reboot_thread("AmbientThread", ambientInterval, "UpdateAmbient")
                elif new_ambient_enabled == ambientEnabled:
                    ambientEnabledLock.release()
                close_menu()
            elif temp_menu == "Ambient Interval":
                # global ambientInterval
                new_ambient_interval = temp_elements[temp_menu_pos]
                ambientInterval = new_ambient_interval
                parser.set('Ambient', 'ambientinterval', str(new_ambient_interval))
                reboot_thread("AmbientThread", new_ambient_interval, "UpdateAmbient")
                close_menu()
            # If we are in the Light sub-menu already, which one of these options was selected
            elif temp_menu == "Light":
                # If Back was selected, return to the Top menu
                if temp_elements[temp_menu_pos] == "Back":
                    change_menu("Top")
                    menuElementsLock.acquire()
                    menuElements = topMenuElements
                    menuElementsLock.release()
                    cursor_to_top()
                # If Light Enabled was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "Light Enabled":
                    change_menu("Light Enabled")
                    # Can only be True or False
                    menuElementsLock.acquire()
                    menuElements = [True, False]
                    menuElementsLock.release()
                    cursor_to_top()
                # If Light Interval was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "Light Interval":
                    change_menu("Light Interval")
                    # Prepare a list of possible quick options for the orientation
                    menuElementsLock.acquire()
                    menuElements = [1, 2, 3, 4, 5, 10, 15, 20, 30, 60]
                    menuElementsLock.release()
                    cursor_to_top()
            elif temp_menu == "Light Interval":
                new_light_interval = temp_elements[temp_menu_pos]
                parser.set('Light', 'lightinterval', str(new_light_interval))
                reboot_thread("LightThread", new_light_interval, "UpdateLight")
                close_menu()
            elif temp_menu == "Light Enabled":
                global lightEnabled
                new_light_enabled = temp_elements[temp_menu_pos]
                parser.set('Light', 'lightenabled', str(new_light_enabled))
                lightEnabledLock.acquire()
                if new_light_enabled != lightEnabled:
                    lightEnabled = new_light_enabled
                    lightEnabledLock.release()
                    if new_light_enabled:
                        reboot_thread("LightThread", lightInterval, "UpdateLight")
                elif new_light_enabled == lightEnabled:
                    lightEnabledLock.release()
                close_menu()
            # If we are in the Accelerometer sub-menu already, which one of these options was selected
            elif temp_menu == "Accelerometer":
                # If Back was selected, return to the Top menu
                if temp_elements[temp_menu_pos] == "Back":
                    change_menu("Top")
                    menuElementsLock.acquire()
                    menuElements = topMenuElements
                    menuElementsLock.release()
                    cursor_to_top()
                # If Accel Enabled was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "Accel Enabled":
                    change_menu("Accel Enabled")
                    # Can only be True or False
                    menuElementsLock.acquire()
                    menuElements = [True, False]
                    menuElementsLock.release()
                    cursor_to_top()
                # If Ambient Interval was selected, go into that sub-menu
                elif temp_elements[temp_menu_pos] == "Accel Interval":
                    change_menu("Accel Interval")
                    # Prepare a list of possible quick options for the orientation
                    menuElementsLock.acquire()
                    menuElements = [1, 2, 3, 4, 5, 10, 15, 20, 30, 60]
                    menuElementsLock.release()
                    cursor_to_top()
            elif temp_menu == "Accel Enabled":
                global accelEnabled
                new_accel_enabled = temp_elements[temp_menu_pos]
                parser.set('Accelerometer', 'accelenabled', str(new_accel_enabled))
                accelEnabledLock.acquire()
                if new_accel_enabled != accelEnabled:
                    accelEnabled = new_accel_enabled
                    accelEnabledLock.release()
                    if new_accel_enabled:
                        reboot_thread("AccelThread", accelInterval, "UpdateAccelerometer")
                elif new_accel_enabled == accelEnabled:
                    accelEnabledLock.release()
                close_menu()
            elif temp_menu == "Accel Interval":
                new_accel_interval = temp_elements[temp_menu_pos]
                parser.set('Accelerometer', 'accelinterval', str(new_accel_interval))
                reboot_thread("AccelThread", new_accel_interval, "UpdateAccelerometer")
                close_menu()
            # If we are in the System sub-menu already, which one of these options was selected
            elif temp_menu == "System":
                global killWatch
                # If Back was selected, return to the Top menu
                if temp_elements[temp_menu_pos] == "Back":
                    change_menu("Top")
                    menuElementsLock.acquire()
                    menuElements = topMenuElements
                    menuElementsLock.release()
                    cursor_to_top()
                # If Shutdown was selected, shutdown the Raspberry Pi
                elif temp_elements[temp_menu_pos] == "Shutdown":
                    kill_program()
                    # Gives the program 5 seconds to wrap things up before shutting down
                    os.system("sudo shutdown -h -t 5")
                # If Reboot was selected, reboot the Raspberry Pi
                elif temp_elements[temp_menu_pos] == "Reboot":
                    kill_program()
                    # Gives the program 5 seconds to wrap things up before rebooting
                    os.system("sudo shutdown -r -t 5")
                # If Kill Program was selected, terminate the program
                elif temp_elements[temp_menu_pos] == "Kill Program":
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
def change_menu(new_menu):
    global currentMenu
    currentMenuLock.acquire()
    currentMenu = new_menu
    currentMenuLock.release()


# Close the LCD configuration menu
def close_menu():
    global inMenu
    inMenuLock.acquire()
    inMenu = False
    inMenuLock.release()


# Brings the pointer arrow on the LCD menu to the top of whatever list is being shown
def cursor_to_top():
    global menuPosition
    menuPositionLock.acquire()
    menuPosition = 0
    menuPositionLock.release()


def get_config_value(name):
    # UI Section
    if name == "defaultorientation":
        defaultOrientationLock.acquire()
        return_value = defaultOrientation
        defaultOrientationLock.release()
    elif name == "lockorientation":
        lockOrientationLock.acquire()
        return_value = lockOrientation
        lockOrientationLock.release()
    elif name == "refreshinterval":
        sleepTimeLock.acquire()
        return_value = sleepTime
        sleepTimeLock.release()
    elif name == "displayenabled":
        displayEnabledLock.acquire()
        return_value = displayEnabled
        displayEnabledLock.release()
    elif name == "printenabled":
        printEnabledLock.acquire()
        return_value = printEnabled
        printEnabledLock.release()
    # General Section
    elif name == "watchedinterface":
        interfaceLock.acquire()
        return_value = watchedInterface
        interfaceLock.release()
    elif name == "cputempinterval":
        cpuTempIntervalLock.acquire()
        return_value = cpuTempInterval
        cpuTempIntervalLock.release()
    elif name == "interfaceinterval":
        interfaceIntervalLock.acquire()
        return_value = interfaceInterval
        interfaceIntervalLock.release()
    elif name == "publicinterval":
        publicIntervalLock.acquire()
        return_value = publicInterval
        publicIntervalLock.release()
    # Requests Section
    elif name == "sendenabled":
        sendEnabledLock.acquire()
        return_value = sendEnabled
        sendEnabledLock.release()
    elif name == "postinterval":
        postIntervalLock.acquire()
        return_value = postInterval
        postIntervalLock.release()
    elif name == "posttimeout":
        postTimeoutLock.acquire()
        return_value = postTimeout
        postTimeoutLock.release()
    elif name == "serverurl":
        serverURLLock.acquire()
        return_value = serverURL
        serverURLLock.release()
    elif name == "iftttkey":
        iftttKeyLock.acquire()
        return_value = iftttKey
        iftttKeyLock.release()
    elif name == "iftttevent":
        iftttEventLock.acquire()
        return_value = iftttEvent
        iftttEventLock.release()
    # Ambient Section
    elif name == "ambientenabled":
        ambientEnabledLock.acquire()
        return_value = ambientEnabled
        ambientEnabledLock.release()
    elif name == "ambientinterval":
        ambientIntervalLock.acquire()
        return_value = ambientInterval
        ambientIntervalLock.release()
    # Light Section
    elif name == "lightenabled":
        lightEnabledLock.acquire()
        return_value = lightEnabled
        lightEnabledLock.release()
    elif name == "lightinterval":
        lightIntervalLock.acquire()
        return_value = lightInterval
        lightIntervalLock.release()
    # Accelerometer Section
    elif name == "accelenabled":
        accelEnabledLock.acquire()
        return_value = accelEnabled
        accelEnabledLock.release()
    elif name == "accelinterval":
        accelIntervalLock.acquire()
        return_value = accelInterval
        accelIntervalLock.release()
    # If variable name wasn't found in the config, return this message
    else:
        return_value = "ConfigNotFound"
    return str(return_value)


def set_config_value(name, value):
    succeeded = False
    if name == "defaultorientation":
        global defaultOrientation
        defaultOrientationLock.acquire()
        try:
            defaultOrientation = int(value)
            parser.set('UI', 'defaultorientation', value)
            succeeded = True
        except TypeError:
            succeeded = False
        finally:
            defaultOrientationLock.release()
    elif name == "lockorientation":
        global lockOrientation
        lockOrientationLock.acquire()
        try:
            lock_bool = bool_check(value)
            if lock_bool == 1:
                lockOrientation = True
                parser.set('UI', 'lockorientation', 'True')
                succeeded = True
            elif lock_bool == 0:
                lockOrientation = False
                parser.set('UI', 'lockorientation', 'False')
                succeeded = True
            elif lock_bool == -1:
                succeeded = False
        except TypeError:
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
    config_list = list()
    # UI Section
    config_list.append({'name': "defaultorientation", 'value': get_config_value("defaultorientation")})
    config_list.append({'name': "lockorientation", 'value': get_config_value("lockorientation")})
    config_list.append({'name': "refreshinterval", 'value': get_config_value("refreshinterval")})
    config_list.append({'name': "displayenabled", 'value': get_config_value("displayenabled")})
    config_list.append({'name': "printenabled", 'value': get_config_value("printenabled")})
    # General Section
    config_list.append({'name': "watchedinterface", 'value': get_config_value("watchedinterface")})
    config_list.append({'name': "cputempinterval", 'value': get_config_value("cputempinterval")})
    config_list.append({'name': "interfaceinterval", 'value': get_config_value("interfaceinterval")})
    config_list.append({'name': "publicinterval", 'value': get_config_value("publicinterval")})
    # Requests Section
    config_list.append({'name': "sendenabled", 'value': get_config_value("sendenabled")})
    config_list.append({'name': "postinterval", 'value': get_config_value("postinterval")})
    config_list.append({'name': "posttimeout", 'value': get_config_value("posttimeout")})
    config_list.append({'name': "serverurl", 'value': get_config_value("serverurl")})
    config_list.append({'name': "iftttkey", 'value': get_config_value("iftttkey")})
    config_list.append({'name': "iftttevent", 'value': get_config_value("iftttevent")})
    # Ambient Section
    config_list.append({'name': "ambientenabled", 'value': get_config_value("ambientenabled")})
    config_list.append({'name': "ambientinterval", 'value': get_config_value("ambientinterval")})
    # Light Section
    config_list.append({'name': "lightenabled", 'value': get_config_value("lightenabled")})
    config_list.append({'name': "lightinterval", 'value': get_config_value("lightinterval")})
    # Accelerometer Section
    config_list.append({'name': "accelenabled", 'value': get_config_value("accelenabled")})
    config_list.append({'name': "accelinterval", 'value': get_config_value("accelinterval")})
    return config_list


def reboot_thread(thread_name, thread_interval, sentinel_name):
    global threads
    if check_sentinel(sentinel_name):
        set_sentinel(sentinel_name, False)
        for t in threads:
            if t.getName() == thread_name:
                t.join()
        set_sentinel(sentinel_name, True)
        new_thread = GeneralThread(len(threads) + 1, thread_name, thread_interval, sentinel_name)
        new_thread.start()
        threads.append(new_thread)


# Displays all the watched variables on the TFT LCD if enabled
def display_values():
    disp.clear()
    # Checks if the orientation of the display should be locked
    # If so, force the default orientation from the config file
    lockOrientationLock.acquire()
    temp_lock_orientation = lockOrientation
    lockOrientationLock.release()
    accelEnabledLock.acquire()
    temp_accel_enabled = accelEnabled
    accelEnabledLock.release()
    if not temp_lock_orientation and temp_accel_enabled:
        orientation = get_mode()
    else:
        defaultOrientationLock.acquire()
        orientation = defaultOrientation
        defaultOrientationLock.release()
    # Depending on the orientation, prepare the display layout image
    if orientation == 0:
        text_draw = Image.new('RGB', (160, 128))
        angle = 90
    elif orientation == 1:
        text_draw = Image.new('RGB', (160, 128))
        angle = 270
    elif orientation == 2:
        text_draw = Image.new('RGB', (128, 160))
        angle = 180
    elif orientation == 3:
        text_draw = Image.new('RGB', (128, 160))
        angle = 0
    else:
        text_draw = Image.new('RGB', (128, 160))
        angle = 90

    # Draw the text objects for all the respective variables by getting
    # the latest values from their Get methods
    text_draw2 = ImageDraw.Draw(text_draw)

    inMenuLock.acquire()
    temp_in_menu = inMenu
    inMenuLock.release()
    if not temp_in_menu:
        text_draw2.text((0, 0), "HW: " + get_serial(), font=font)
        rtc_time = get_date_time()
        dat = "Date: " + str(rtc_time.date) + "/" + str(rtc_time.month) + "/" + str(
            rtc_time.year)  # convert to string and print it
        text_draw2.text((0, 12), dat, font=font)
        tmr = "Time: " + '{:02d}'.format(rtc_time.hour) + ":" + '{:02d}'.format(rtc_time.min) + ":" + '{:02d}'.format(
            rtc_time.sec)  # convert to string and print it
        text_draw2.text((0, 24), tmr, font=font)
        text_draw2.text((0, 36), "Light: " + str(get_light()) + " lx", font=font)
        text_draw2.text((0, 48), "Temp: " + str(get_ambient_temp()) + " C", font=font)
        text_draw2.text((0, 60), "Press: " + str(get_ambient_pressure()) + " kPa", font=font)
        text_draw2.text((0, 72), "CPU Temp: " + str(get_cpu_temp()) + " C", font=font)
        text_draw2.text((0, 84), "LAN IP: " + str(get_watched_interface_ip()), font=font)
        text_draw2.text((0, 96), "WAN IP: " + str(get_public_ip()), font=font)
        # text_draw2.text((0, 108), "Button Pressed: " + str(GetButton()), font=font)
        text_draw2.text((0, 108), "X: " + str(get_accel_x()) + " Y: " + str(get_accel_y()) + " Z: " +
                        str(get_accel_z()), font=font)
    else:
        menuElementsLock.acquire()
        temp_elements = menuElements
        menuElementsLock.release()
        for x in range(0, 10):
            try:
                text_draw2.text((18, x * 12), str(temp_elements[x]), font=font)
            except IndexError:
                break
        menuPositionLock.acquire()
        temp_menu_pos = menuPosition
        menuPositionLock.release()
        text_draw2.text((0, temp_menu_pos * 12), ">>", font=font)

    # Rotate the image to the set orientation and add it to the LCD
    text_draw3 = text_draw.rotate(angle)
    canvas = Image.new("RGB", (128, 160))
    canvas.paste(text_draw3, (0, 0))
    disp.display(canvas)


# Prints all the watched variables to the console if enabled
def print_values():
    options = {-1: "Not Ready",
               0: "Landscape Left",
               1: "Landscape Right",
               2: "Portrait Up",
               3: "Portrait Down"
               }
    # Get the current date and time and the latest update of all the watched
    # variables and print them to the console
    rtc_time = get_date_time()
    print("HW: " + get_serial())
    print("Date: " + str(rtc_time.date) + "/" + str(rtc_time.month) + "/" + str(
        rtc_time.year))  # convert to string and print it
    print("Time: " + '{:02d}'.format(rtc_time.hour) + ":" + '{:02d}'.format(rtc_time.min) + ":" + '{:02d}'.format(
        rtc_time.sec))
    print("Light: " + str(get_light()) + " lx")
    print("Temp: " + str(get_ambient_temp()) + " C")
    print("Pressure: " + str(get_ambient_pressure()) + " kPa")
    print("CPU Temp: " + str(get_cpu_temp()) + " C")
    print("LAN IP: " + str(get_watched_interface_ip()))
    print("WAN IP: " + get_public_ip())
    print("Mode: " + options[get_mode()])
    print("Button Pressed: " + str(get_button()))
    print("--------------------")


# POST the variables in JSON format to the URL specified in the config file
def send_values():
    rtc_time = get_date_time()
    time_string = "20" + '{:02d}'.format(rtc_time.year) + "-" + '{:02d}'.format(rtc_time.month) + "-" + '{:02d}'.format(
        rtc_time.date) + " " + '{:02d}'.format(rtc_time.hour) + ":" + '{:02d}'.format(
        rtc_time.min) + ":" + '{:02d}'.format(rtc_time.sec)
    # Prepare a JSON of the variables
    payload = {'HW': str(get_serial()),
               'TS': time_string,
               'IP': str(get_watched_interface_ip()),
               'CPU': str(get_cpu_temp()),
               'LUX': str(get_light()),
               'Temp': str(get_ambient_temp()),
               'Press': str(get_ambient_pressure()),
               'X': str(old_div(get_accel_x(), 1000.0)),
               'Y': str(old_div(get_accel_y(), 1000.0)),
               'Z': str(old_div(get_accel_z(), 1000.0))
               }
    # Attempt to POST the JSON to the given URL, catching any failures
    postTimeoutLock.acquire()
    temp_timeout = postTimeout
    postTimeoutLock.release()
    try:
        requests.post(serverURL, data=json.dumps(payload), timeout=temp_timeout)
        # print r.text #For debugging POST requests
    except requests.ConnectionError:
        print("POST ERROR - Check connection and server")


# Method names for the threads to call to update their variables
methods = {"UpdateDateTime": update_date_time,
           "UpdateAmbient": update_ambient,
           "UpdateLight": update_light,
           "UpdateCPUTemp": update_cpu_temp,
           "UpdateWatchedInterfaceIP": update_watched_interface_ip,
           "UpdatePublicIP": update_public_ip,
           "UpdateAccelerometer": update_accelerometer,
           "UpdateButton": update_button,
           "SendValues": send_values,
           }


# Method to read the config file or set defaults if parameters missing
def config():
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
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
        except configparser.NoSectionError:
            parser.add_section('Requests')
            parser.set('Requests', 'iftttevent', iftttEvent)
    finally:
        print("IFTTT Event: " + iftttEvent)

    # Write the config file back to disk with the given values and
    # filling in any blanks with the defaults
    write_config()

    print("-------------------------")


# Writes any changes to the config file back to disk whenever changes are made
def write_config():
    with open('client.cfg', 'w') as configfile:
        parser.write(configfile)
        os.system("chmod 777 client.cfg")


# Main Method
def main():
    # CPU serial shouldn't change so it is only updated once
    update_serial()

    # Create threads and start them to monitor the various sensors and
    # IP variables at their given intervals, 1 second interval for time/buttons
    reboot_thread("TimeThread", 1, "UpdateDateTime")
    reboot_thread("AmbientThread", ambientInterval, "UpdateAmbient")
    reboot_thread("LightThread", lightInterval, "UpdateLight")
    reboot_thread("CPUTempThread", cpuTempInterval, "UpdateCPUTemp")
    reboot_thread("InterfaceIPThread", interfaceInterval, "UpdateWatchedInterfaceIP")
    reboot_thread("PublicIPThread", publicInterval, "UpdatePublicIP")
    reboot_thread("AccelThread", accelInterval, "UpdateAccelerometer")
    reboot_thread("SendThread", postInterval, "SendValues")

    flaskEnabledLock.acquire()
    temp_flask_enabled = flaskEnabled
    flaskEnabledLock.release()
    if temp_flask_enabled:
        flask_thread = FlaskThread()
        flask_thread.start()

    # Set up the GPIO for the touch buttons and LED
    GPIO.setup(CAP_PIN, GPIO.IN)
    GPIO.setup(LED_PIN, GPIO.OUT)
    GPIO.add_event_detect(CAP_PIN, GPIO.FALLING)
    GPIO.add_event_callback(CAP_PIN, button_event_handler)

    # Enable interrupts on the buttons
    CapTouch.clearInterrupt()
    CapTouch.enableInterrupt(0, 0, 0x07)

    killWatchLock.acquire()
    temp_kill_watch = killWatch
    killWatchLock.release()

    # Loop the display and/or printing of variables if desired, waiting between
    # calls for the set or default refresh interval
    while not temp_kill_watch:
        printEnabledLock.acquire()
        temp_print_enabled = printEnabled
        printEnabledLock.release()
        if temp_print_enabled:
            print_values()

        displayEnabledLock.acquire()
        temp_display_enabled = displayEnabled
        displayEnabledLock.release()
        if temp_display_enabled:
            display_values()

        sleepTimeLock.acquire()
        temp_sleep_time = sleepTime
        sleepTimeLock.release()
        time.sleep(temp_sleep_time)

        killWatchLock.acquire()
        temp_kill_watch = killWatch
        killWatchLock.release()


# Assuming this program is run itself, execute normally
if __name__ == "__main__":
    # Initialize variables once by reading or creating the config file
    config()
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

        write_config()

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
