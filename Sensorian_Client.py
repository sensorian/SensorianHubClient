#!/usr/bin/python

"""Sensorian_Client.py: Collects sensor data on given intervals and sends it to various services upon request.

Cab be run on its own or imported to other projects and run in the background.
"""

from __future__ import print_function
import ConfigParser
import os
import requests
import json
import time
import datetime
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
import TFT as GLCD
import APDS9300 as LUX_SENSOR
import MPL3115A2 as ALTIBAR
import CAP1203 as CAP_TOUCH
import MCP79410RTCC as RT_CLOCK
import FXOS8700CQR1 as ACCEL_SENSOR
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
from sense_hat import SenseHat

__author__ = "Dylan Kauling"
__maintainer__ = "Dylan Kauling"
__status__ = "Development"


CapTouch = None
RTC = None
imuSensor = None
AltiBar = None
font = None
disp = None
sensehat = None

def sensorian_setup():
    # Sensor initializations

    # RTC excepts on first call on boot
    # Loops until the RTC works
    rtc_not_ready = True
    global RTC
    while rtc_not_ready:
        try:
            RTC = RT_CLOCK.MCP79410()
            rtc_not_ready = False
        except:
            rtc_not_ready = True

    global imuSensor
    imuSensor = ACCEL_SENSOR.FXOS8700CQR1()
    imuSensor.configureAccelerometer()
    imuSensor.configureMagnetometer()
    imuSensor.configureOrientation()
    global AltiBar
    AltiBar = ALTIBAR.MPL3115A2()
    AltiBar.ActiveMode()
    AltiBar.BarometerMode()
    # print "Giving the Barometer 2 seconds or it won't work"
    time.sleep(2)
    global CapTouch
    CapTouch = CAP_TOUCH.CAP1203()

    # Prepare an object for drawing on the TFT LCD
    global disp
    disp = GLCD.TFT()
    disp.initialize()
    disp.clear()
    global font
    font = ImageFont.truetype('/usr/share/fonts/truetype/freefont/FreeSansBold.ttf', 14)  # use a truetype font

    # Set up the GPIO for the touch buttons and LED
    GPIO.setup(CAP_PIN, GPIO.IN)
    GPIO.setup(LED_PIN, GPIO.OUT)
    GPIO.add_event_detect(CAP_PIN, GPIO.FALLING)
    GPIO.add_event_callback(CAP_PIN, button_event_handler)

    # Enable interrupts on the buttons
    CapTouch.clearInterrupt()
    CapTouch.enableInterrupt(0, 0, 0x07)


def sense_hat_setup():
    global sensehat
    sensehat = SenseHat()


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
flaskEnabled = False
socketEnabled = False
magnetEnabled = True

# Global sensor/IP variables protected by locks below if required
currentDateTime = datetime.datetime(2000, 1, 1, 0, 0, 0)
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
hatEnabled = True
hatUsed = "Sensorian"
defaultOrientation = 0
sleepTime = 1
postInterval = 4
postTimeout = 5
ambientInterval = 5
lightInterval = 1
cpuTempInterval = 5
interfaceInterval = 5
publicInterval = 30
accelInterval = 1
inMenu = False
currentMenu = "Top"
menuElements = []
topMenuElements = ["Exit", "General", "UI", "Requests", "Accelerometer", "Light", "Ambient", "System"]
menuPosition = 0
parser = ConfigParser.SafeConfigParser()
threads = []
killWatch = False
magnetX = 0
magnetY = 0
magnetZ = 0
magnetInterval = 1
configUsername = 'configUsername'
configPassword = 'configPassword'
relayAddress = "0.0.0.0"
relayPort = 8000

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
watchedInterfaceLock = threading.Lock()
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
socketEnabledLock = threading.Lock()
magnetXLock = threading.Lock()
magnetYLock = threading.Lock()
magnetZLock = threading.Lock()
magnetIntervalLock = threading.Lock()
magnetEnabledLock = threading.Lock()
relayAddressLock = threading.Lock()
relayPortLock = threading.Lock()
configUsernameLock = threading.Lock()
configPasswordLock = threading.Lock()
hatEnabledLock = threading.Lock()
hatUsedLock = threading.Lock()

app = Flask(__name__)
api = Api(app)
auth = HTTPBasicAuth()


@auth.get_password
def get_password(username):
    """Used by Flask HTTP Auth to validate a username and password when requesting a secure page.

    Accepts a single username and password from the config file.
    """
    configUsernameLock.acquire()
    temp_config_username = configUsername
    configUsernameLock.release()
    if username == temp_config_username:
        configPasswordLock.acquire()
        temp_config_password = configPassword
        configPasswordLock.release()
        return temp_config_password
    return None


class ConfigListAPI(Resource):
    """Flask RESTful API for listing all current config values.

    Execute a GET request to http://0.0.0.0/variables to retrieve the list.
    """
    decorators = [auth.login_required]

    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument('name', type=str, location='json')
        self.reqparse.add_argument('value', type=str, location='json')
        super(ConfigListAPI, self).__init__()

    def get(self):
        config_list = get_all_config()
        return {'variables': config_list}


class ConfigAPI(Resource):
    """Flask RESTful API for checking and updating specific config values.

    Execute a GET or PUT request to http://0.0.0.0/variables/variablename to retrieve or set the item.
    """
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
    """Method called by the Flask Thread to start the Flask server.

    Runs the Flask server in debug mode currently and binds to any interface.
    Can be called directly as well if not already running.
    """
    print("Running Flask")
    app.run(debug=True, use_reloader=False, host='0.0.0.0')


def shutdown_server():
    """Method called  by kill_flask() to shut down the Flask server if it is running.

    Called on application close or upon POST request to /shutdown, should not be called directly!
    """
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()


@app.route('/shutdown', methods=['POST'])
@auth.login_required
def shutdown_flask_api():
    """Flask API to shut down the Flask server.

    This of course prevents future calls to the Flask API.
    Requires Basic Authentication with config username and password.
    """
    shutdown_server()
    return 'Flask server shutting down...'


@app.route('/commands/kill', methods=['POST'])
@auth.login_required
def kill_client_api():
    """Flask API to kill the Sensorian Hub Client gracefully.

    This of course prevents future calls to the Client.
    Requires Basic Authentication with config username and password.
    """
    kill_program()
    return 'Sensorian Client shutting down...'


@app.route('/commands/shutdown', methods=['POST'])
@auth.login_required
def shutdown_pi_api():
    """Flask API to shutdown the Raspberry Pi.

    This of course prevents future calls to the Client.
    Requires Basic Authentication with config username and password.
    """
    shutdown_pi()
    return 'Raspberry Pi shutting down...'


@app.route('/commands/reboot', methods=['POST'])
@auth.login_required
def reboot_pi_api():
    """Flask API to shutdown the Raspberry Pi.

    This of course prevents future calls to the Client until it is started again.
    Requires Basic Authentication with config username and password.
    """
    reboot_pi()
    return 'Raspberry Pi rebooting...'


def kill_flask():
    """Method to shut down the Flask server.

    Called on system shutdown by cleanup() but can be called directly as well.
    This makes a POST to the shutdown URL authenticated with the config file username and password.
    Needs to be called for shutdown_server() to work.
    """
    url = 'http://127.0.0.1:5000/shutdown'
    configUsernameLock.acquire()
    temp_config_username = configUsername
    configUsernameLock.release()
    configPasswordLock.acquire()
    temp_config_password = configPassword
    configPasswordLock.release()
    try:
        requests.post(url, auth=(temp_config_username, temp_config_password))
    except requests.exceptions.ConnectionError:
        print("Flask server already shut down")


def update_serial():
    """Updates the global CPU serial variable by reading it from the cpuinfo file.

    Really only needs to be called once when the Client is initialized. It's not going to change.
    """
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


def get_serial():
    """Gets the CPU serial from the global variable when not locked.

    :return: String of the CPU serial.
    """
    serialLock.acquire()
    temp_serial = cpuSerial
    serialLock.release()
    return temp_serial


class GeneralThread(threading.Thread):
    """General Thread class to repeatedly update a variable at a given interval

    Takes an arbitrary int thread_id and string name to identify the thread.
    Takes an integer or float interval for how long in seconds to wait between updating values.
    Takes the string method which is the name of the method to call contained in the methods dictionary.
    """
    # Initializes a thread upon creation
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
    """A Thread class specifically to run a Flask server in the background.

    Terminates when an authenticated POST to /shutdown is made or shutdown_server() is called.
    """
    def __init__(self):
        """Initializes a Flask Thread with only a default ID and name.
        """
        threading.Thread.__init__(self)
        self.threadID = 99
        self.name = "FlaskThread"

    def run(self):
        """Runs a Flask server continuously until terminated.

        Can be terminated by an authenticated POST to /shutdown or call of shutdown_server().
        """
        run_flask()
        print("Killing FlaskThread")


class SocketThread(threading.Thread):
    """A Thread class specifically to establish a socket with a Sensorian Hub Site relay server.

    The socket code is kind of janky with no real schema yet, but allows for configuration behind NATs and firewalls.
    """
    def __init__(self):
        """Initializes the Socket thread with the config values for address, port and defaults for timings and ID/name.
        """
        threading.Thread.__init__(self)
        self.threadID = 100
        self.name = "SocketThread"
        self.connected = False
        self.host = get_config_value("relayaddress")
        self.port = get_config_value("relayport")
        self.repeat = check_sentinel("SocketSentinel")
        self.slept = 0
        self.keep_alive = 5
        self.timeout = 5.0

    def run(self):
        """Loops attempts to establish a socket and waits for commands from the server when one is established.

        Can be terminated by setting the SocketSentinel to False.
        """
        while self.repeat:
            if not self.connected:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(self.timeout)
                    s.connect((self.host, self.port))
                    self.connected = True
                except socket.timeout:
                    self.connected = False
            if self.slept >= self.keep_alive:
                s.send("KeepAlive")
                message = s.recv(1024)
                if message == "LIVE":
                    print("LIVE Received")
                elif message == "PREPARE":
                    s.send("READY")
                    data = s.recv(1024)
                    if data == "CANCEL":
                        print("CANCEL Received")
                    elif data:
                        try:
                            colon = data.index(":")
                            config_temp = get_config_value(data[0:colon])
                            if config_temp != "ConfigNotFound":
                                set_temp = set_config_value(data[0:colon], data[colon + 1:len(data) + 1])
                                if set_temp:
                                    print("Updated " + data[0:colon] + " to " + get_config_value(data[0:colon]))
                                else:
                                    print("Did not update " + data[0:colon] + ", stays " + get_config_value(
                                        data[0:colon]))
                            else:
                                print("Did not find variable named " + data[0:colon])
                        except ValueError:
                            print("Malformed data received from socket")
                self.slept = 0
            elif self.slept < self.keep_alive:
                self.slept += 1
            self.repeat = check_sentinel("SocketSentinel")
            time.sleep(1)
        s.close()
        print("Killing SocketThread")


def update_light():
    """Updates the global light variable by reading the Lux value from the Sensorian ambient light sensor.

    This is called by the Light Thread, but can be called directly as well.
    """
    global light
    if get_config_value("hatenabled") == "True":
        if get_config_value("hatused") == "Sensorian":
            temp_light = -1
            I2CLock.acquire()
            # Try to initialize and update the light value
            # Sometimes it excepts, so catch it if it does
            try:
                ambient_light = LUX_SENSOR.APDS9300()
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
        elif get_config_value("hatused") == "Sense HAT":
            lightLock.acquire()
            light = -1
            lightLock.release()


def get_light():
    """Gets the most recent update of the global light variable when not locked.

    :return: Float of the last updated light value.
    """
    lightLock.acquire()
    try:
        temp_light = light
    finally:
        lightLock.release()
    return temp_light


def get_ambient_temp():
    """Gets the most recent update of the global ambient temperature variable when not locked.

    :return: Float of the last updated ambient temperature.
    """
    ambientTempLock.acquire()
    return_temp = ambientTemp
    ambientTempLock.release()
    return return_temp


def get_ambient_pressure():
    """Gets the most recent update of the global barometric pressure variable when not locked.

    :return: Float of the last updated barometric pressure.
    """
    ambientPressureLock.acquire()
    return_press = float(ambientPressure) / 1000
    ambientPressureLock.release()
    return return_press


def update_ambient():
    """Updates the global ambient temperature and pressure variables by using the Sensorian Altibar sensor.

    This is called by the Ambient Thread, but can be called directly as well.
    """
    global ambientTemp
    global ambientPressure
    if get_config_value("hatenabled") == "True":
        if get_config_value("hatused") == "Sensorian":
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
        elif get_config_value("hatused") == "Sense HAT":
            # Update the ambient temperature global variable
            I2CLock.acquire()
            temp = sensehat.temperature
            I2CLock.release()
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
                press = sensehat.pressure
                I2CLock.release()
                ambientPressureLock.acquire()
                ambientPressure = press
                ambientPressureLock.release()
            else:
                print("NoPressureNeeded")


def update_date_time():
    """Updates the global RTC date/time object by polling the date and time from the Sensorian real-time clock.

    This is called by the Time Thread, but can be called directly as well.
    """
    global currentDateTime
    if get_config_value("hatenabled") == "True":
        if get_config_value("hatused") == "Sensorian":
            I2CLock.acquire()
            temp_date_time = RTC.GetTime()
            I2CLock.release()
            temp_date = datetime.date(2000 + temp_date_time.year, temp_date_time.month, temp_date_time.date)
            temp_time = datetime.time(temp_date_time.hour, temp_date_time.min, temp_date_time.sec)
            temp_datetime = datetime.datetime.combine(temp_date, temp_time)
            rtcLock.acquire()
            currentDateTime = temp_datetime
            rtcLock.release()
        elif get_config_value("hatused") == "Sense HAT":
            rtcLock.acquire()
            currentDateTime = datetime.datetime.now()
            rtcLock.release()
        else:
            rtcLock.acquire()
            currentDateTime = datetime.datetime.now()
            rtcLock.release()
    else:
        rtcLock.acquire()
        currentDateTime = datetime.datetime.now()
        rtcLock.release()


def get_date_time():
    """Gets the most recent update of the global RTC date/time object when not locked.

    :return: RTC date/time object containing the last updated date and time.
    """
    rtcLock.acquire()
    temp_date_time = currentDateTime
    rtcLock.release()
    return temp_date_time


def update_cpu_temp():
    """Updates the global CPU temperature variable by reading the value from the system temperature file.

    This is called by the CPU Thread, but can be called directly as well.
    """
    # Read the CPU temperature from the system file
    global cpuTemp
    temp_path = '/sys/class/thermal/thermal_zone0/temp'
    temp_file = open(temp_path)
    cpu = temp_file.read()
    temp_file.close()
    temp = (float(cpu) / 1000)
    # Update the global variable when safe
    cpuTempLock.acquire()
    cpuTemp = temp
    cpuTempLock.release()


def get_cpu_temp():
    """Gets the most recent update of the global CPU temperature variable when not locked.

    :return: Float containing the last updated CPU temperature in Celcius.
    """
    cpuTempLock.acquire()
    temp = cpuTemp
    cpuTempLock.release()
    return temp


def update_watched_interface_ip():
    """Updates the global Watched Network Interface IP variable by calling get_interface_ip().

    This is called by the Update Watched IP Thread, but can be called directly as well.
    """
    global interfaceIP
    watchedInterfaceLock.acquire()
    temp_interface = watchedInterface
    watchedInterfaceLock.release()
    ipaddr = get_interface_ip(temp_interface)
    interfaceIPLock.acquire()
    interfaceIP = ipaddr
    interfaceIPLock.release()
    if get_config_value("hatenabled") == "True":
        if get_config_value("hatused") == "Sense HAT":
            sensehat.show_message("IP: " + ipaddr)


def get_watched_interface_ip():
    """Gets the most recent update of the global watched network interface IP variable when not locked.

    :return: String of the watched network interface's IP from the last update.
    """
    interfaceIPLock.acquire()
    temp_ip = interfaceIP
    interfaceIPLock.release()
    return temp_ip


def get_interface_ip(interface):
    """Gets the IP of the network interface passed by establishing and reading on socket on that interface.

    This is called by update_watched_interface_ip() with the watched interface, but can be called directly as well.
    :param interface: String of the network interface to check, eg. eth0, wlan0, etc.
    :return: String of the given network interface's IP, defaults to 0.0.0.0
    """
    # Create a socket to use to query the interface
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Try to get the IP of the passed interface
    try:
        ipaddr = socket.inet_ntoa(fcntl.ioctl(
            s.fileno(),
            0x8915,  # SIOCGIFADDR
            struct.pack('256s', interface[:15])
        )[20:24])
    # If it fails, return an empty IP address
    except IOError:
        ipaddr = "0.0.0.0"
    # Close the socket whether an IP was found or not
    finally:
        s.close()
    # Return the IP Address: Correct or Empty
    return ipaddr


def update_public_ip():
    """Updates the global Public IP variable by calling curl on icanhazip.com

    Called by Update Public IP Thread, but can be called directly as well.
    Gets the IP from icanhazip.com. As with any Internet resource, please be respectful.
    Ie. Don't update too frequently, that's not cool.
    """
    global publicIP
    # Initiate a subprocess to run a curl request for the public IP
    proc = subprocess.Popen(["curl", "-s", "-4", "icanhazip.com"], stdout=subprocess.PIPE)
    (out, err) = proc.communicate()
    # Store the response of the request when safe
    publicIPLock.acquire()
    publicIP = out.rstrip()
    publicIPLock.release()


def get_public_ip():
    """Gets the most recent update of the global public IP variable when not locked.

    :return: String of the public IP of the Client from the last update.
    """
    publicIPLock.acquire()
    temp_ip = publicIP
    publicIPLock.release()
    return temp_ip


def update_accelerometer():
    """Updates all the various Accelerometer-related global variables by polling the Sensorian's Accelerometer.

    This is called by the Accel Thread, but can be called directly as well.
    """
    global mode, modeprevious, accelX, accelY, accelZ
    if get_config_value("hatenabled") == "True":
        if get_config_value("hatused") == "Sensorian":
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
        elif get_config_value("hatused") == "Sense HAT":
            I2CLock.acquire()
            temp_accel = sensehat.accelerometer_raw
            I2CLock.release()
            x = temp_accel.get('x')
            y = temp_accel.get('y')
            z = temp_accel.get('z')
            accelXLock.acquire()
            accelX = x
            accelXLock.release()
            accelYLock.acquire()
            accelY = y
            accelYLock.release()
            accelZLock.acquire()
            accelZ = z
            accelZLock.release()


def update_magnetometer():
    """Updates all the various Magnetometer-related global variables by polling the Sensorian's Magnetometer.

    This is called by the Magnet Thread, but can be called directly as well.
    """
    global magnetX, magnetY, magnetZ
    if get_config_value("hatenabled") == "True":
        if get_config_value("hatused") == "Sensorian":
            I2CLock.acquire()
            # If the magnetometer is ready, read the magnetic forces
            if imuSensor.readStatusReg() & 0x80:
                magnet_x, magnet_y, magnet_z = imuSensor.pollMagnetometer()
                I2CLock.release()
                # Store the various global variables when safe
                magnetXLock.acquire()
                magnetX = magnet_x
                magnetXLock.release()
                magnetYLock.acquire()
                magnetY = magnet_y
                magnetYLock.release()
                magnetZLock.acquire()
                magnetZ = magnet_z
                magnetZLock.release()
            else:
                I2CLock.release()
        elif get_config_value("hatused") == "Sense HAT":
            I2CLock.acquire()
            temp_mag = sensehat.compass_raw
            I2CLock.release()
            magnet_x = temp_mag.get('x')
            magnet_y = temp_mag.get('y')
            magnet_z = temp_mag.get('z')
            magnetXLock.acquire()
            magnetX = magnet_x
            magnetXLock.release()
            magnetYLock.acquire()
            magnetY = magnet_y
            magnetYLock.release()
            magnetZLock.acquire()
            magnetZ = magnet_z
            magnetZLock.release()


def get_mag_x():
    """Gets the most recent update of the global magnetic force x variable when not locked.

    :return: Integer of the last updated magnetic force in the X direction
    """
    magnetXLock.acquire()
    x = magnetX
    magnetXLock.release()
    return x


def get_mag_y():
    """Gets the most recent update of the global magnetic force y variable when not locked.

    :return: Integer of the last updated magnetic force in the Y direction
    """
    magnetYLock.acquire()
    y = magnetY
    magnetYLock.release()
    return y


def get_mag_z():
    """Gets the most recent update of the global magnetic force z variable when not locked.

    :return: Integer of the last updated magnetic force in the Z direction
    """
    magnetZLock.acquire()
    z = magnetZ
    magnetZLock.release()
    return z


def get_mode():
    """Gets the most recent update of the global orientation variable when not locked.

    :return: Integer of the last updated orientation
    """
    modeLock.acquire()
    temp_mode = mode
    modeLock.release()
    return temp_mode


def get_accel_x():
    """Gets the most recent update of the global acceleration x variable when not locked.

    :return: Integer of the last updated acceleration in the X direction
    """
    accelXLock.acquire()
    x = accelX
    accelXLock.release()
    return x


def get_accel_y():
    """Gets the most recent update of the global acceleration y variable when not locked.

    :return: Integer of the last updated acceleration in the Y direction
    """
    accelYLock.acquire()
    y = accelY
    accelYLock.release()
    return y


def get_accel_z():
    """Gets the most recent update of the global acceleration z variable when not locked.

    :return: Integer of the last updated acceleration in the Z direction
    """
    accelZLock.acquire()
    z = accelZ
    accelZLock.release()
    return z


def button_event_handler(pin):
    """Method that is called when an interrupt is generated on the Sensorian Capacitive Button interrupt pin.

    Updates the global button variable with the button pressed and calls the button_handler with that button.
    Called by the interrupt event exclusively. Could be called directly with CAP_PIN passed with unknown results.
    :param pin: Pin number that the interrupt event came from, passed by the event.
    """
    # Confirms that the interrupt came from the button pin just
    # so your IDE doesn't complain about pin going unused
    if pin == CAP_PIN:
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


def get_button():
    """Gets the number of the button pressed from the last update/interrupt.

    :return: Integer of which was the last button pressed.
    """
    buttonLock.acquire()
    temp_button = button
    buttonLock.release()
    return temp_button


def check_sentinel(sentinel):
    """Checks the current state of the global sentinel boolean variable passed to the method.

    Called by threads to check if they should be started at boot/continue executing.
    Can be called directly to check the current state of these sentinel variables safely.
    :param sentinel: String name of the Sentinel variable to be checked.
    :return: Boolean of the state of the sentinel checked, defaults to False if not found.
    """
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
    elif sentinel == "ButtonEnabled":
        buttonEnabledLock.acquire()
        state = buttonEnabled
        buttonEnabledLock.release()
    elif sentinel == "SendValues":
        sendEnabledLock.acquire()
        state = sendEnabled
        sendEnabledLock.release()
    elif sentinel == "SocketSentinel":
        socketEnabledLock.acquire()
        state = socketEnabled
        socketEnabledLock.release()
    elif sentinel == "UpdateMagnetometer":
        magnetEnabledLock.acquire()
        state = magnetEnabled
        magnetEnabledLock.release()
    else:
        state = False
    return state


def set_sentinel(sentinel, state):
    """Sets the current state of the global sentinel boolean variable passed to the method to the passed state.

    Called in cleanup() to terminate all the threads at the end of the Client's execution.
    Can be called directly to stop a specific thread or to prepare a thread to be started.
    :param sentinel: String name of the Sentinel variable to be set.
    :param state: Boolean state to which the Sentinel variable will be set.
    """
    global timeEnabled, ambientEnabled, lightEnabled, cpuEnabled, interfaceIPEnabled, publicIPEnabled, \
        accelEnabled, buttonEnabled, sendEnabled, socketEnabled, magnetEnabled
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
    elif sentinel == "ButtonEnabled":
        buttonEnabledLock.acquire()
        buttonEnabled = state
        buttonEnabledLock.release()
    elif sentinel == "SendValues":
        sendEnabledLock.acquire()
        sendEnabled = state
        sendEnabledLock.release()
    elif sentinel == "SocketSentinel":
        socketEnabledLock.acquire()
        socketEnabled = state
        socketEnabledLock.release()
    elif sentinel == "UpdateMagnetometer":
        magnetEnabledLock.acquire()
        magnetEnabled = state
        magnetEnabledLock.release()


def ifttt_trigger(key="xxxxxxxxxxxxxxxxxxxxxx", event="SensorianEvent", timeout=5, value1="", value2="", value3=""):
    """Sends a request to an IFTTT Maker Channel with the given key and event name.

    A valid IFTTT Maker Channel API key is required and can be obtained from https://ifttt.com/maker.
    An event name is required to trigger a specific recipe created using the Maker Channel.
    Extra values included in the JSON payload are optional, but can be used to tune the result of a recipe.
    A timeout in seconds is optional, defaults to 5 seconds.
    Interacts with ifttt.com. As with any Internet resource, please be respectful.
    Ie. Don't trigger too frequently, that's not cool.
    """
    payload = {'value1': str(value1), 'value2': str(value2), 'value3': str(value3)}
    url = "https://maker.ifttt.com/trigger/" + event + "/with/key/" + key
    # Make a GET request to the IFTTT maker channel URL using the event name and key
    try:
        r = requests.post(url, data=payload, timeout=timeout)
        print(r.text)  # For debugging GET requests
    except requests.exceptions.ConnectionError:
        print("IFTTT ERROR - requests.exceptions.ConnectionError - Check connection and server")
    except requests.exceptions.InvalidSchema:
        print("IFTTT ERROR - requests.exceptions.InvalidSchema - Check the URL")
    except requests.exceptions.Timeout:
        print("IFTTT TIMEOUT - requests.exceptions.Timeout - Please try again or check connection")


def get_menu_elements():
    """Gets a list of the current menu elements global variable to be displayed on the LCD.

    Called when the menu is displayed/refreshed.
    :return: String List of the current menu elements.
    """
    menuElementsLock.acquire()
    temp_elements = menuElements
    menuElementsLock.release()
    return temp_elements


def set_menu_elements(new_list):
    """Sets a new list to the current menu elements global variable to be displayed on the LCD.

    Called when the menu level is changed.
    :param new_list: String list of the new current menu elements.
    """
    global menuElements
    menuElementsLock.acquire()
    menuElements = new_list
    menuElementsLock.release()


def button_handler(pressed):
    """Handles button presses on the Sensorian Shield to fire an event or display/interact with a local config menu.

    Called by button_event_handler() when a button interrupt is received.
    Could be called directly to automate menu interactions for demonstration purposes.
    :param pressed: Integer of the last button pressed.
    """
    if check_sentinel("ButtonEnabled"):
        global inMenu
        global currentMenu
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
                set_menu_elements(topMenuElements)
                cursor_to_top()
            elif pressed == 1:
                ifttt_trigger(key=iftttKey, event="SensorianButton1", value1=get_serial())
            elif pressed == 3:
                ifttt_trigger(key=iftttKey, event="SensorianButton3", value1=get_serial())
        else:
            print("Menu Pressed " + str(pressed))
            currentMenuLock.acquire()
            temp_menu = currentMenu
            currentMenuLock.release()
            temp_elements = get_menu_elements()
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
                # If it was the top menu, which menu option was selected
                if temp_menu == "Top":
                    # If Exit was selected, close the menu
                    if temp_elements[temp_menu_pos] == "Exit":
                        close_menu()
                    # If General was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "General":
                        change_menu("General")
                        set_menu_elements(["Back", "Watched Interface", "CPU Temp Interval", "Interface Interval",
                                           "Public Interval"])
                        cursor_to_top()
                    # If UI was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "UI":
                        change_menu("UI")
                        set_menu_elements(["Back", "Default Orientation", "Lock Orientation", "Refresh Interval",
                                           "Display Enabled", "Print Enabled"])
                        cursor_to_top()
                    # If Requests was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "Requests":
                        change_menu("Requests")
                        set_menu_elements(["Back", "POST Enabled", "POST Interval", "POST Timeout", "Server URL",
                                           "IFTTT Key", "IFTTT Event"])
                        cursor_to_top()
                    # If Ambient was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "Ambient":
                        change_menu("Ambient")
                        set_menu_elements(["Back", "Ambient Enabled", "Ambient Interval"])
                        cursor_to_top()
                    # If Light was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "Light":
                        change_menu("Light")
                        set_menu_elements(["Back", "Light Enabled", "Light Interval"])
                        cursor_to_top()
                    # If Accelerometer was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "Accelerometer":
                        change_menu("Accelerometer")
                        set_menu_elements(["Back", "Accel Enabled", "Accel Interval"])
                        cursor_to_top()
                    # If System was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "System":
                        change_menu("System")
                        set_menu_elements(["Back", "Shutdown", "Reboot", "Kill Program"])
                        cursor_to_top()
                # If we are in the general sub-menu already, which one of these options was selected
                elif temp_menu == "General":
                    # If Back was selected, return to the Top menu
                    if temp_elements[temp_menu_pos] == "Back":
                        change_menu("Top")
                        set_menu_elements(topMenuElements)
                        cursor_to_top()
                    # If Watched Interface was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "Watched Interface":
                        change_menu("Watched Interface")
                        # Get the list of watchable interfaces before pulling up the menu
                        proc = subprocess.Popen(["ls", "-1", "/sys/class/net"], stdout=subprocess.PIPE)
                        (out, err) = proc.communicate()
                        interfaces = out.rstrip()
                        interfaces_list = interfaces.split()
                        set_menu_elements(interfaces_list)
                        cursor_to_top()
                    # If CPU Temp Interval was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "CPU Temp Interval":
                        change_menu("CPU Temp Interval")
                        # Prepare a list of possible quick options for the interval
                        set_menu_elements(['1', '2', '3', '4', '5', '10', '15', '20', '30', '60'])
                        cursor_to_top()
                    # If Interface Interval was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "Interface Interval":
                        change_menu("Interface Interval")
                        # Prepare a list of possible quick options for the interval
                        set_menu_elements(['1', '2', '3', '4', '5', '10', '15', '20', '30', '60'])
                        cursor_to_top()
                    # If Public Interval was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "Public Interval":
                        change_menu("Public Interval")
                        # Prepare a list of possible quick options for the interval
                        set_menu_elements(['10', '15', '20', '30', '60', '120', '240', '360', '480', '600'])
                        cursor_to_top()
                # If an option was selected in the Watched Interface menu, update the config parser with the new value
                # as well as the global variable, no need to reboot the thread as it checks which interface each time
                elif temp_menu == "Watched Interface":
                    new_interface = temp_elements[temp_menu_pos]
                    set_config_value('watchedinterface', new_interface)
                    close_menu()
                # If an option was selected in the following menus, update the config parser with the new value
                # to be written on close and reboot the respective monitoring thread with the new value
                elif temp_menu == "CPU Temp Interval":
                    new_temp_interval = temp_elements[temp_menu_pos]
                    set_config_value('cputempinterval', new_temp_interval)
                    close_menu()
                elif temp_menu == "Interface Interval":
                    new_interface_interval = temp_elements[temp_menu_pos]
                    set_config_value('interfaceinterval', new_interface_interval)
                    close_menu()
                elif temp_menu == "Public Interval":
                    new_public_interval = temp_elements[temp_menu_pos]
                    set_config_value('publicinterval', new_public_interval)
                    close_menu()
                # If we are in the UI sub-menu already, which one of these options was selected
                elif temp_menu == "UI":
                    # If Back was selected, return to the Top menu
                    if temp_elements[temp_menu_pos] == "Back":
                        change_menu("Top")
                        set_menu_elements(topMenuElements)
                        cursor_to_top()
                    # If Default Orientation was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "Default Orientation":
                        change_menu("Default Orientation")
                        # Prepare a list of possible quick options for the orientation
                        set_menu_elements(["0 = Landscape Left", "1 = Landscape Right",
                                           "2 = Portrait Up", "3 = Portrait Down"])
                        cursor_to_top()
                    # If Lock Orientation was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "Lock Orientation":
                        change_menu("Lock Orientation")
                        # Can only be True or False
                        set_menu_elements(['True', 'False'])
                        cursor_to_top()
                    # If Refresh Interval was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "Refresh Interval":
                        change_menu("Refresh Interval")
                        # Prepare a list of possible quick options for the interval
                        set_menu_elements(['0.1', '0.25', '0.5', '0.75', '1', '1.5', '2', '2.5', '5', '10'])
                        cursor_to_top()
                    # If Display Enabled was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "Display Enabled":
                        change_menu("Display Enabled")
                        # Can only be True or False
                        set_menu_elements(['True', 'False'])
                        cursor_to_top()
                    # If Print Enabled was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "Print Enabled":
                        change_menu("Print Enabled")
                        # Can only be True or False
                        set_menu_elements(['True', 'False'])
                        cursor_to_top()
                elif temp_menu == "Default Orientation":
                    new_orientation_string = temp_elements[temp_menu_pos]
                    new_orientation_sub = new_orientation_string[0]
                    set_config_value('defaultorientation', new_orientation_sub)
                    close_menu()
                elif temp_menu == "Lock Orientation":
                    new_lock_orientation = temp_elements[temp_menu_pos]
                    set_config_value('lockorientation', new_lock_orientation)
                    close_menu()
                elif temp_menu == "Refresh Interval":
                    new_refresh_interval = temp_elements[temp_menu_pos]
                    set_config_value('refreshinterval', new_refresh_interval)
                    close_menu()
                elif temp_menu == "Display Enabled":
                    new_display_enabled = temp_elements[temp_menu_pos]
                    set_config_value('displayenabled', new_display_enabled)
                    close_menu()
                elif temp_menu == "Print Enabled":
                    new_print_enabled = temp_elements[temp_menu_pos]
                    set_config_value('printenabled', new_print_enabled)
                    close_menu()
                # If we are in the Requests sub-menu already, which one of these options was selected
                elif temp_menu == "Requests":
                    # If Back was selected, return to the Top menu
                    if temp_elements[temp_menu_pos] == "Back":
                        change_menu("Top")
                        set_menu_elements(topMenuElements)
                        cursor_to_top()
                    # If POST Enabled was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "POST Enabled":
                        change_menu("POST Enabled")
                        # Can only be True or False
                        set_menu_elements(['True', 'False'])
                        cursor_to_top()
                    # If POST Interval was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "POST Interval":
                        change_menu("POST Interval")
                        # Prepare a list of possible quick options for the orientation
                        set_menu_elements(['1', '2', '3', '4', '5', '10', '15', '20', '30', '60'])
                        cursor_to_top()
                    # If POST Timeout was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "POST Timeout":
                        change_menu("POST Interval")
                        # Prepare a list of possible quick options for the orientation
                        set_menu_elements(['1', '2', '3', '4', '5', '10', '15', '20', '30', '60'])
                        cursor_to_top()
                elif temp_menu == "POST Enabled":
                    new_send_enabled = temp_elements[temp_menu_pos]
                    set_config_value('sendenabled', new_send_enabled)
                    close_menu()
                elif temp_menu == "POST Interval":
                    new_post_interval = temp_elements[temp_menu_pos]
                    set_config_value('postinterval', new_post_interval)
                    close_menu()
                elif temp_menu == "POST Timeout":
                    new_post_timeout = temp_elements[temp_menu_pos]
                    set_config_value('posttimeout', new_post_timeout)
                    close_menu()
                # If we are in the Ambient sub-menu already, which one of these options was selected
                elif temp_menu == "Ambient":
                    # If Back was selected, return to the Top menu
                    if temp_elements[temp_menu_pos] == "Back":
                        change_menu("Top")
                        set_menu_elements(topMenuElements)
                        cursor_to_top()
                    # If Ambient Enabled was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "Ambient Enabled":
                        change_menu("Ambient Enabled")
                        # Can only be True or False
                        set_menu_elements(['True', 'False'])
                        cursor_to_top()
                    # If Ambient Interval was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "Ambient Interval":
                        change_menu("Ambient Interval")
                        # Prepare a list of possible quick options for the orientation
                        set_menu_elements(['1', '2', '3', '4', '5', '10', '15', '20', '30', '60'])
                        cursor_to_top()
                elif temp_menu == "Ambient Enabled":
                    new_ambient_enabled = temp_elements[temp_menu_pos]
                    set_config_value('ambientenabled', new_ambient_enabled)
                    close_menu()
                elif temp_menu == "Ambient Interval":
                    new_ambient_interval = temp_elements[temp_menu_pos]
                    set_config_value('ambientinterval', new_ambient_interval)
                    close_menu()
                # If we are in the Light sub-menu already, which one of these options was selected
                elif temp_menu == "Light":
                    # If Back was selected, return to the Top menu
                    if temp_elements[temp_menu_pos] == "Back":
                        change_menu("Top")
                        set_menu_elements(topMenuElements)
                        cursor_to_top()
                    # If Light Enabled was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "Light Enabled":
                        change_menu("Light Enabled")
                        # Can only be True or False
                        set_menu_elements(['True', 'False'])
                        cursor_to_top()
                    # If Light Interval was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "Light Interval":
                        change_menu("Light Interval")
                        # Prepare a list of possible quick options for the orientation
                        set_menu_elements(['1', '2', '3', '4', '5', '10', '15', '20', '30', '60'])
                        cursor_to_top()
                elif temp_menu == "Light Interval":
                    new_light_interval = temp_elements[temp_menu_pos]
                    set_config_value('lightinterval', new_light_interval)
                    close_menu()
                elif temp_menu == "Light Enabled":
                    new_light_enabled = temp_elements[temp_menu_pos]
                    set_config_value('lightenabled', new_light_enabled)
                    close_menu()
                # If we are in the Accelerometer sub-menu already, which one of these options was selected
                elif temp_menu == "Accelerometer":
                    # If Back was selected, return to the Top menu
                    if temp_elements[temp_menu_pos] == "Back":
                        change_menu("Top")
                        set_menu_elements(topMenuElements)
                        cursor_to_top()
                    # If Accel Enabled was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "Accel Enabled":
                        change_menu("Accel Enabled")
                        # Can only be True or False
                        set_menu_elements(['True', 'False'])
                        cursor_to_top()
                    # If Ambient Interval was selected, go into that sub-menu
                    elif temp_elements[temp_menu_pos] == "Accel Interval":
                        change_menu("Accel Interval")
                        # Prepare a list of possible quick options for the orientation
                        set_menu_elements(['1', '2', '3', '4', '5', '10', '15', '20', '30', '60'])
                        cursor_to_top()
                elif temp_menu == "Accel Enabled":
                    new_accel_enabled = temp_elements[temp_menu_pos]
                    set_config_value('accelenabled', new_accel_enabled)
                    close_menu()
                elif temp_menu == "Accel Interval":
                    new_accel_interval = temp_elements[temp_menu_pos]
                    set_config_value('accelinterval', new_accel_interval)
                    close_menu()
                # If we are in the System sub-menu already, which one of these options was selected
                elif temp_menu == "System":
                    global killWatch
                    # If Back was selected, return to the Top menu
                    if temp_elements[temp_menu_pos] == "Back":
                        change_menu("Top")
                        set_menu_elements(topMenuElements)
                        cursor_to_top()
                    # If Shutdown was selected, shutdown the Raspberry Pi
                    elif temp_elements[temp_menu_pos] == "Shutdown":
                        # Gives the program 5 seconds to wrap things up before shutting down
                        shutdown_pi()
                    # If Reboot was selected, reboot the Raspberry Pi
                    elif temp_elements[temp_menu_pos] == "Reboot":
                        # Gives the program 5 seconds to wrap things up before rebooting
                        reboot_pi()
                    # If Kill Program was selected, terminate the program
                    elif temp_elements[temp_menu_pos] == "Kill Program":
                        kill_program()


def kill_program():
    """Signals the Client to terminate gracefully by setting the kill sentinel to True.

    Called by the local menu, Flask API or the shutdown/reboot functions, but can be called directly as well.
    """
    global killWatch
    killWatchLock.acquire()
    killWatch = True
    killWatchLock.release()


def shutdown_pi():
    """Signals the Raspberry Pi to shut down in 5 seconds to give the Client time to wrap up.

    Calls kill_program() first to terminate the Client gracefully then shutdown_pi_helper() to shut down.
    Called by the local menu or Flask API but can be called directly as well.
    """
    kill_program()
    shutdown_helper = Process(target=shutdown_pi_helper)
    shutdown_helper.start()


def shutdown_pi_helper():
    """Calls the helper shutdown.py script with the halt and 5 second time parameters to shut down the Pi in 5 seconds.

    Should not be called directly if the Client is already running.
    """
    os.system("sudo python shutdown.py -h --time=5")


def reboot_pi():
    """Signals the Raspberry Pi to reboot in 5 seconds to give the Client time to wrap up.

    Calls kill_program() first to terminate the Client gracefully then reboot_pi_helper() to reboot.
    Called by the local menu or Flask API but can be called directly as well.
    """
    kill_program()
    reboot_helper = Process(target=reboot_pi_helper)
    reboot_helper.start()


def reboot_pi_helper():
    """Calls the helper shutdown.py script with the reboot and 5 second time parameters to reboot the Pi in 5 seconds.

    Should not be called directly if the Client is already running.
    """
    os.system("sudo python shutdown.py -r --time=5")


def change_menu(new_menu):
    """Changes the menu to be displayed on the LCD by passing the name of the new menu to be set to the global variable.

    :param new_menu: String name of the new menu to be displayed on the LCD.
    """
    global currentMenu
    currentMenuLock.acquire()
    currentMenu = new_menu
    currentMenuLock.release()


def close_menu():
    """Closes the LCD local configuration menu by setting the global inMenu variable to False.

    Called when Exit or a new value or action is selected, but can be called directly as well for demo purposes.
    """
    global inMenu
    inMenuLock.acquire()
    inMenu = False
    inMenuLock.release()


def cursor_to_top():
    """Brings the pointer arrow on the LCD menu to the top of whatever list is being shown

    Called when displaying a new menu or looping back around from the bottom of a menu.
    """
    global menuPosition
    menuPositionLock.acquire()
    menuPosition = 0
    menuPositionLock.release()


def get_config_value(name):
    """Gets the current value of the passed config variable name.

    Functionality may be combined/reorganized with that of check_sentinel() in the future.
    :param name: String name of the config value to be checked. Naming matches that of the config file.
    :return: String of the current value of the config variable, needs to be casted back if string not desired.
    """
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
        watchedInterfaceLock.acquire()
        return_value = watchedInterface
        watchedInterfaceLock.release()
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
    elif name == "relayaddress":
        relayAddressLock.acquire()
        return_value = relayAddress
        relayAddressLock.release()
    elif name == "relayport":
        relayPortLock.acquire()
        return_value = relayPort
        relayPortLock.release()
    elif name == "configusername":
        configUsernameLock.acquire()
        return_value = configUsername
        configUsernameLock.release()
    elif name == "configpassword":
        configPasswordLock.acquire()
        return_value = configPassword
        configPasswordLock.release()
    elif name == "hatenabled":
        hatEnabledLock.acquire()
        return_value = hatEnabled
        hatEnabledLock.release()
    elif name == "hatused":
        hatUsedLock.acquire()
        return_value = hatUsed
        hatUsedLock.release()
    # If variable name wasn't found in the config, return this message
    else:
        return_value = "ConfigNotFound"
    return str(return_value)


def set_config_value(name, value):
    """Sets a config value in both the Config Parser memory and Client memory with a passed name and new value.

    Functionality may be combined/reorganized with that of set_sentinel() in the future.
    :param name: String name of the config value to be set. Naming matches that of the config file.
    :param value: String value of the new value to be set to the config variable. Auto-casted to the appropriate type.
    :return: Boolean of if the set operation was successful or not. Could fail for unknown variable or wrong data type.
    """
    succeeded = False
    global defaultOrientation, lockOrientation, sleepTime, displayEnabled, printEnabled, watchedInterface, \
        cpuTempInterval, interfaceInterval, publicInterval, sendEnabled, postInterval, postTimeout, serverURL, \
        iftttKey, iftttEvent, ambientEnabled, ambientInterval, lightEnabled, lightInterval, accelEnabled, \
        accelInterval, relayAddress, relayPort, configUsername, configPassword, hatEnabled, hatUsed
    # UI Section
    if name == "defaultorientation":
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
        lockOrientationLock.acquire()
        lock_bool = bool_check(str(value))
        if lock_bool[0]:
            lockOrientation = lock_bool[1]
            parser.set('UI', 'lockorientation', str(lock_bool[1]))
            succeeded = True
        elif not lock_bool[0]:
            succeeded = False
        lockOrientationLock.release()
    elif name == "refreshinterval":
        sleepTimeLock.acquire()
        try:
            sleepTime = float(value)
            parser.set('UI', 'refreshinterval', value)
            succeeded = True
        except TypeError:
            succeeded = False
        finally:
            sleepTimeLock.release()
    elif name == "displayenabled":
        displayEnabledLock.acquire()
        lock_bool = bool_check(str(value))
        if lock_bool[0]:
            displayEnabled = lock_bool[1]
            parser.set('UI', 'displayenabled', str(lock_bool[1]))
            succeeded = True
        elif not lock_bool[0]:
            succeeded = False
        displayEnabledLock.release()
    elif name == "printenabled":
        printEnabledLock.acquire()
        lock_bool = bool_check(str(value))
        if lock_bool[0]:
            printEnabled = lock_bool[1]
            parser.set('UI', 'printenabled', str(lock_bool[1]))
            succeeded = True
        elif not lock_bool[0]:
            succeeded = False
        printEnabledLock.release()
    # General Section
    elif name == "watchedinterface":
        watchedInterfaceLock.acquire()
        try:
            watchedInterface = value
            parser.set('General', 'watchedinterface', value)
            succeeded = True
        except TypeError:
            succeeded = False
        finally:
            watchedInterfaceLock.release()
    elif name == "cputempinterval":
        cpuTempIntervalLock.acquire()
        try:
            cpuTempInterval = float(value)
            parser.set('General', 'cputempinterval', value)
            reboot_thread("CPUTempThread", cpuTempInterval, "UpdateCPUTemp")
            succeeded = True
        except TypeError:
            succeeded = False
        finally:
            cpuTempIntervalLock.release()
    elif name == "interfaceinterval":
        interfaceIntervalLock.acquire()
        try:
            interfaceInterval = float(value)
            parser.set('General', 'interfaceinterval', value)
            reboot_thread("InterfaceIPThread", interfaceInterval, "UpdateWatchedInterfaceIP")
            succeeded = True
        except TypeError:
            succeeded = False
        finally:
            interfaceIntervalLock.release()
    elif name == "publicinterval":
        publicIntervalLock.acquire()
        try:
            publicInterval = float(value)
            parser.set('General', 'publicinterval', value)
            reboot_thread("PublicIPThread", publicInterval, "UpdatePublicIP")
            succeeded = True
        except TypeError:
            succeeded = False
        finally:
            publicIntervalLock.release()
    # Requests Section
    elif name == "sendenabled":
        lock_bool = bool_check(str(value))
        if lock_bool[0]:
            sendEnabledLock.acquire()
            if lock_bool[1] != sendEnabled:
                sendEnabled = lock_bool[1]
                sendEnabledLock.release()
                if lock_bool[1]:
                    postIntervalLock.acquire()
                    temp_post_interval = postInterval
                    postIntervalLock.release()
                    reboot_thread("SendThread", temp_post_interval, "SendValues")
            parser.set('Requests', 'sendenabled', str(lock_bool[1]))
            succeeded = True
        elif not lock_bool[0]:
            succeeded = False
    elif name == "postinterval":
        postIntervalLock.acquire()
        try:
            postInterval = float(value)
            parser.set('Requests', 'postinterval', value)
            reboot_thread("SendThread", postInterval, "SendValues")
            succeeded = True
        except TypeError:
            succeeded = False
        finally:
            postIntervalLock.release()
    elif name == "posttimeout":
        postTimeoutLock.acquire()
        try:
            postTimeout = float(value)
            parser.set('Requests', 'posttimeout', value)
            succeeded = True
        except TypeError:
            succeeded = False
        finally:
            postTimeoutLock.release()
    elif name == "serverurl":
        serverURLLock.acquire()
        try:
            serverURL = value
            parser.set('Requests', 'serverurl', value)
            succeeded = True
        except TypeError:
            succeeded = False
        finally:
            serverURLLock.release()
    elif name == "iftttkey":
        iftttKeyLock.acquire()
        try:
            iftttKey = value
            parser.set('Requests', 'iftttkey', value)
            succeeded = True
        except TypeError:
            succeeded = False
        finally:
            iftttKeyLock.release()
    elif name == "iftttevent":
        iftttEventLock.acquire()
        try:
            iftttEvent = value
            parser.set('Requests', 'iftttevent', value)
            succeeded = True
        except TypeError:
            succeeded = False
        finally:
            iftttEventLock.release()
    # Ambient Section
    elif name == "ambientenabled":
        lock_bool = bool_check(str(value))
        if lock_bool[0]:
            ambientEnabledLock.acquire()
            if lock_bool[1] != ambientEnabled:
                ambientEnabled = lock_bool[1]
                ambientEnabledLock.release()
                if lock_bool[1]:
                    ambientIntervalLock.acquire()
                    temp_ambient_interval = ambientInterval
                    ambientIntervalLock.release()
                    reboot_thread("AmbientThread", temp_ambient_interval, "UpdateAmbient")
            parser.set('Ambient', 'ambientenabled', str(lock_bool[1]))
            succeeded = True
        elif not lock_bool[0]:
            succeeded = False
    elif name == "ambientinterval":
        ambientIntervalLock.acquire()
        try:
            ambientInterval = float(value)
            parser.set('Ambient', 'ambientinterval', value)
            reboot_thread("AmbientThread", ambientInterval, "UpdateAmbient")
            succeeded = True
        except TypeError:
            succeeded = False
        finally:
            ambientIntervalLock.release()
    # Light Section
    elif name == "lightenabled":
        lock_bool = bool_check(str(value))
        if lock_bool[0]:
            lightEnabledLock.acquire()
            if lock_bool[1] != lightEnabled:
                lightEnabled = lock_bool[1]
                lightEnabledLock.release()
                if lock_bool[1]:
                    lightIntervalLock.acquire()
                    temp_light_interval = lightInterval
                    lightIntervalLock.release()
                    reboot_thread("LightThread", temp_light_interval, "UpdateLight")
            parser.set('Light', 'lightenabled', str(lock_bool[1]))
            succeeded = True
        elif not lock_bool[0]:
            succeeded = False
    elif name == "lightinterval":
        lightIntervalLock.acquire()
        try:
            lightInterval = float(value)
            parser.set('Light', 'lightinterval', value)
            reboot_thread("LightThread", lightInterval, "UpdateLight")
            succeeded = True
        except TypeError:
            succeeded = False
        finally:
            lightIntervalLock.release()
    # Accelerometer Section
    elif name == "accelenabled":
        lock_bool = bool_check(str(value))
        if lock_bool[0]:
            accelEnabledLock.acquire()
            if lock_bool[1] != accelEnabled:
                accelEnabled = lock_bool[1]
                accelEnabledLock.release()
                if lock_bool[1]:
                    accelIntervalLock.acquire()
                    temp_accel_interval = accelInterval
                    accelIntervalLock.release()
                    reboot_thread("AccelThread", temp_accel_interval, "UpdateAccelerometer")
            parser.set('Accelerometer', 'accelenabled', str(lock_bool[1]))
            succeeded = True
        elif not lock_bool[0]:
            succeeded = False
    elif name == "accelinterval":
        accelIntervalLock.acquire()
        try:
            accelInterval = float(value)
            parser.set('Accelerometer', 'accelinterval', value)
            reboot_thread("AccelThread", accelInterval, "UpdateAccelerometer")
            succeeded = True
        except TypeError:
            succeeded = False
        finally:
            accelIntervalLock.release()
    elif name == "relayaddress":
        relayAddressLock.acquire()
        try:
            relayAddress = value
            parser.set('RemoteConfig', 'relayaddress', value)
            succeeded = True
        except TypeError:
            succeeded = False
        finally:
            relayAddressLock.release()
    elif name == "relayport":
        relayPortLock.acquire()
        try:
            validate = int(value)
            if 1 <= validate <= 65535:
                relayPort = int(value)
                parser.set('RemoteConfig', 'relayport', value)
                succeeded = True
            else:
                succeeded = False
        except TypeError:
            succeeded = False
        finally:
            relayPortLock.release()
    elif name == "configusername":
        configUsernameLock.acquire()
        try:
            configUsername = value
            parser.set('RemoteConfig', 'configusername', value)
            succeeded = True
        except TypeError:
            succeeded = False
        finally:
            configUsernameLock.release()
    elif name == "configpassword":
        configPasswordLock.acquire()
        try:
            configPassword = value
            parser.set('RemoteConfig', 'configpassword', value)
            succeeded = True
        except TypeError:
            succeeded = False
        finally:
            configPasswordLock.release()
    elif name == "hatenabled":
        hatEnabledLock.acquire()
        lock_bool = bool_check(str(value))
        if lock_bool[0]:
            hatEnabled = lock_bool[1]
            parser.set('Sensors', 'hatenabled', str(lock_bool[1]))
            succeeded = True
        elif not lock_bool[0]:
            succeeded = False
        hatEnabledLock.release()
    elif name == "hatused":
        hatUsedLock.acquire()
        try:
            hatUsed = value
            parser.set('Sensors', 'hatused', value)
            succeeded = True
        except TypeError:
            succeeded = False
        finally:
            hatUsedLock.release()
    return succeeded


def bool_check(value):
    """Helper function for checking if the passed String is a valid boolean state.

    :param value: String value to be checked for boolean status.
    :return: 2-boolean list, with the first boolean indicating if it's a boolean and if so its value in the second item.
    """
    if value in ['True', 'true', 'TRUE', 'T', 't', 'Y', 'y', '1']:
        return [True, True]
    elif value in ['False', 'false', 'FALSE', 'F', 'f', 'N', 'n', '0']:
        return [True, False]
    else:
        return [False, False]


def get_all_config():
    """Gets a list of all the config file variable names and values in dictionary format.

    Called by ConfigListAPI() when all variables are GET requested.
    :return: List of all the config file variable names and values in dictionary format.
    """
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
    # Sensor Section
    config_list.append({'name': "hatenabled", 'value': get_config_value("hatenabled")})
    config_list.append({'name': "hatused", 'value': get_config_value("hatused")})
    # Requests Section
    config_list.append({'name': "sendenabled", 'value': get_config_value("sendenabled")})
    config_list.append({'name': "postinterval", 'value': get_config_value("postinterval")})
    config_list.append({'name': "posttimeout", 'value': get_config_value("posttimeout")})
    config_list.append({'name': "serverurl", 'value': get_config_value("serverurl")})
    config_list.append({'name': "iftttkey", 'value': get_config_value("iftttkey")})
    config_list.append({'name': "iftttevent", 'value': get_config_value("iftttevent")})
    # Remote Config Section
    config_list.append({'name': "relayaddress", 'value': get_config_value("relayaddress")})
    config_list.append({'name': "relayport", 'value': get_config_value("relayport")})
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
    """Reboots a thread with a new interval, or starts it if not running in the first place.

    Called in setup() when the Client is started or in set_config_value() when a thread should be started.
    :param thread_name: String name of the thread to start. Defined in methods.
    :param thread_interval: Integer/Float of how often to update the value in seconds.
    :param sentinel_name: String name of the sentinel which determines if the thread should be running.
    """
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


def display_values():
    """Displays the watched variables on the LCD or the menu if it is active.

    Called on a loop in the main method when enabled to keep refreshing the screen, but can be called directly as well.
    """
    if get_config_value("hatenabled") == "True":
        if get_config_value("hatused") == "Sensorian":
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
                dat = "Date: " + str(rtc_time.day) + "/" + str(rtc_time.month) + "/" + str(
                    rtc_time.year)  # convert to string and print it
                text_draw2.text((0, 12), dat, font=font)
                tmr = "Time: " + '{:02d}'.format(rtc_time.hour) + ":" + '{:02d}'.format(rtc_time.minute) + \
                      ":" + '{:02d}'.format(rtc_time.second)  # convert to string and print it
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


def print_values():
    """Prints all the watched variables to the console/standard output.

    Called on a loop in the main method if enabled to keep refreshing the values, but can be called directly as well.
    """
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
    print("Date: " + str(rtc_time.day) + "/" + str(rtc_time.month) + "/" + str(
        rtc_time.year))  # convert to string and print it
    print("Time: " + '{:02d}'.format(rtc_time.hour) + ":" + '{:02d}'.format(rtc_time.minute) + ":" + '{:02d}'.format(
        rtc_time.second))
    print("Light: " + str(get_light()) + " lx")
    print("Temp: " + str(get_ambient_temp()) + " C")
    print("Pressure: " + str(get_ambient_pressure()) + " kPa")
    print("CPU Temp: " + str(get_cpu_temp()) + " C")
    print("LAN IP: " + str(get_watched_interface_ip()))
    print("WAN IP: " + get_public_ip())
    print("Mode: " + options[get_mode()])
    print("Button Pressed: " + str(get_button()))
    print("--------------------")


def send_values():
    """POSTs the watched variables in JSON format to the URL specified in the config file.

    Called by the Send Thread on a regular interval if enabled, but can be called directly as well.
    """
    rtc_time = get_date_time()
    time_string = '{:04d}'.format(rtc_time.year) + "-" + '{:02d}'.format(rtc_time.month) + "-" + '{:02d}'.format(
        rtc_time.day) + " " + '{:02d}'.format(rtc_time.hour) + ":" + '{:02d}'.format(
        rtc_time.minute) + ":" + '{:02d}'.format(rtc_time.second)
    # Prepare a JSON of the variables
    if get_config_value("hatenabled") == "True" and get_config_value("hatused") == "Sensorian":
        accel_x = get_accel_x() / 1000.0
        accel_y = get_accel_y() / 1000.0
        accel_z = get_accel_z() / 1000.0
    else:
        accel_x = get_accel_x()
        accel_y = get_accel_y()
        accel_z = get_accel_z()

    payload = {'HW': str(get_serial()),
               'TS': time_string,
               'IP': str(get_watched_interface_ip()),
               'CPU': str(get_cpu_temp()),
               'LUX': str(get_light()),
               'Temp': str(get_ambient_temp()),
               'Press': str(get_ambient_pressure()),
               'X': str(accel_x),
               'Y': str(accel_y),
               'Z': str(accel_z)
               }
    # Attempt to POST the JSON to the given URL, catching any failures
    serverURLLock.acquire()
    temp_url = serverURL
    serverURLLock.release()
    postTimeoutLock.acquire()
    temp_timeout = postTimeout
    postTimeoutLock.release()
    try:
        post_request = requests.post(temp_url, data=json.dumps(payload), timeout=temp_timeout)
        print(post_request.text)  # For debugging POST requests
    except requests.ConnectionError:
        print("POST ERROR - Check connection and server")
    except requests.exceptions.Timeout:
        print("POST TIMEOUT - Please try again or check connection")


# Method names for the threads to call to update their variables
methods = {"UpdateDateTime": update_date_time,
           "UpdateAmbient": update_ambient,
           "UpdateLight": update_light,
           "UpdateCPUTemp": update_cpu_temp,
           "UpdateWatchedInterfaceIP": update_watched_interface_ip,
           "UpdatePublicIP": update_public_ip,
           "UpdateAccelerometer": update_accelerometer,
           "SendValues": send_values,
           "UpdateMagnetometer": update_magnetometer
           }


def config():
    """Reads the client.cfg configuration file and sets global variables from it or default values if missing.

    Called on startup to initialize the Client from the config file, but can be called directly to read it again.
    """
    print("-------------------------")
    print("Configuring Settings")
    global parser
    parser = ConfigParser.SafeConfigParser()
    # Read the config file if present
    parser.read('client.cfg')

    # The following similar blocks of code check every variable that should
    # be in the config file, setting the global variable for it if it exists
    # and setting it to default if it does not
    global defaultOrientation
    try:
        defaultOrientation = parser.getint('UI', 'defaultorientation')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('UI', 'defaultorientation', str(defaultOrientation))
        except ConfigParser.NoSectionError:
            parser.add_section('UI')
            parser.set('UI', 'defaultorientation', str(defaultOrientation))
    finally:
        print("Default Orientation: " + str(defaultOrientation))

    global lockOrientation
    try:
        lockOrientation = parser.getboolean('UI', 'lockorientation')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('UI', 'lockorientation', str(lockOrientation))
        except ConfigParser.NoSectionError:
            parser.add_section('UI')
            parser.set('UI', 'lockorientation', str(lockOrientation))
    finally:
        print("Lock Orientation: " + str(lockOrientation))

    global sleepTime
    try:
        sleepTime = parser.getfloat('UI', 'refreshinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('UI', 'refreshinterval', str(sleepTime))
        except ConfigParser.NoSectionError:
            parser.add_section('UI')
            parser.set('UI', 'refreshinterval', str(sleepTime))
    finally:
        print("Refresh Interval: " + str(sleepTime))

    global watchedInterface
    try:
        watchedInterface = parser.get('General', 'watchedinterface')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('General', 'watchedinterface', watchedInterface)
        except ConfigParser.NoSectionError:
            parser.add_section('General')
            parser.set('General', 'watchedinterface', watchedInterface)
    finally:
        print("Watched Interface: " + watchedInterface)

    global sendEnabled
    try:
        sendEnabled = parser.getboolean('Requests', 'sendenabled')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Requests', 'sendenabled', str(sendEnabled))
        except ConfigParser.NoSectionError:
            parser.add_section('Requests')
            parser.set('Requests', 'sendenabled', str(sendEnabled))
    finally:
        print("Send Enabled: " + str(sendEnabled))

    global postInterval
    try:
        postInterval = parser.getfloat('Requests', 'postinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Requests', 'postinterval', str(postInterval))
        except ConfigParser.NoSectionError:
            parser.add_section('Requests')
            parser.set('Requests', 'postinterval', str(postInterval))
    finally:
        print("POST Interval: " + str(postInterval))

    global postTimeout
    try:
        postTimeout = parser.getfloat('Requests', 'posttimeout')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Requests', 'posttimeout', str(postTimeout))
        except ConfigParser.NoSectionError:
            parser.add_section('Requests')
            parser.set('Requests', 'posttimeout', str(postTimeout))
    finally:
        print("POST Timeout: " + str(postTimeout))

    global ambientEnabled
    try:
        ambientEnabled = parser.getboolean('Ambient', 'ambientenabled')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Ambient', 'ambientenabled', str(ambientEnabled))
        except ConfigParser.NoSectionError:
            parser.add_section('Ambient')
            parser.set('Ambient', 'ambientenabled', str(ambientEnabled))
    finally:
        print("Ambient Enabled: " + str(ambientEnabled))

    global ambientInterval
    try:
        ambientInterval = parser.getfloat('Ambient', 'ambientinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Ambient', 'ambientinterval', str(ambientInterval))
        except ConfigParser.NoSectionError:
            parser.add_section('Ambient')
            parser.set('Ambient', 'ambientinterval', str(ambientInterval))
    finally:
        print("Ambient Interval: " + str(ambientInterval))

    global lightEnabled
    try:
        lightEnabled = parser.getboolean('Light', 'lightenabled')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Light', 'lightenabled', str(lightEnabled))
        except ConfigParser.NoSectionError:
            parser.add_section('Light')
            parser.set('Light', 'lightenabled', str(lightEnabled))
    finally:
        print("Light Enabled: " + str(lightEnabled))

    global lightInterval
    try:
        lightInterval = parser.getfloat('Light', 'lightinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Light', 'lightinterval', str(lightInterval))
        except ConfigParser.NoSectionError:
            parser.add_section('Light')
            parser.set('Light', 'lightinterval', str(lightInterval))
    finally:
        print("Light Interval: " + str(lightInterval))

    global cpuTempInterval
    try:
        cpuTempInterval = parser.getfloat('General', 'cputempinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('General', 'cputempinterval', str(cpuTempInterval))
        except ConfigParser.NoSectionError:
            parser.add_section('General')
            parser.set('General', 'cputempinterval', str(cpuTempInterval))
    finally:
        print("CPU Temp Interval: " + str(cpuTempInterval))

    global interfaceInterval
    try:
        interfaceInterval = parser.getfloat('General', 'interfaceinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('General', 'interfaceinterval', str(interfaceInterval))
        except ConfigParser.NoSectionError:
            parser.add_section('General')
            parser.set('General', 'interfaceinterval', str(interfaceInterval))
    finally:
        print("Local IP Interval: " + str(interfaceInterval))

    global publicInterval
    try:
        publicInterval = parser.getfloat('General', 'publicinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('General', 'publicinterval', str(publicInterval))
        except ConfigParser.NoSectionError:
            parser.add_section('General')
            parser.set('General', 'publicinterval', str(publicInterval))
    finally:
        print("Public IP Interval: " + str(publicInterval))

    global hatEnabled
    try:
        hatEnabled = parser.getboolean('Sensors', 'hatenabled')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Sensors', 'hatenabled', str(hatEnabled))
        except ConfigParser.NoSectionError:
            parser.add_section('Sensors')
            parser.set('Sensors', 'hatenabled', str(hatEnabled))
    finally:
        print("Hat Enabled: " + str(hatEnabled))

    global hatUsed
    try:
        hatUsed = parser.get('Sensors', 'hatused')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Sensors', 'hatused', hatUsed)
        except ConfigParser.NoSectionError:
            parser.add_section('Sensors')
            parser.set('Sensors', 'hatused', hatUsed)
    finally:
        print("Hat Used: " + hatUsed)

    global accelEnabled
    try:
        accelEnabled = parser.getboolean('Accelerometer', 'accelenabled')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Accelerometer', 'accelenabled', str(accelEnabled))
        except ConfigParser.NoSectionError:
            parser.add_section('Accelerometer')
            parser.set('Accelerometer', 'accelenabled', str(accelEnabled))
    finally:
        print("Accel Enabled: " + str(accelEnabled))

    global accelInterval
    try:
        accelInterval = parser.getfloat('Accelerometer', 'accelinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Accelerometer', 'accelinterval', str(accelInterval))
        except ConfigParser.NoSectionError:
            parser.add_section('Accelerometer')
            parser.set('Accelerometer', 'accelinterval', str(accelInterval))
    finally:
        print("Accelerometer Interval: " + str(accelInterval))

    global displayEnabled
    try:
        displayEnabled = parser.getboolean('UI', 'displayenabled')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('UI', 'displayenabled', str(displayEnabled))
        except ConfigParser.NoSectionError:
            parser.add_section('UI')
            parser.set('UI', 'displayenabled', str(displayEnabled))
    finally:
        print("Display Enabled: " + str(displayEnabled))

    global printEnabled
    try:
        printEnabled = parser.getboolean('UI', 'printenabled')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('UI', 'printenabled', str(printEnabled))
        except ConfigParser.NoSectionError:
            parser.add_section('UI')
            parser.set('UI', 'printenabled', str(printEnabled))
    finally:
        print("Print Enabled: " + str(printEnabled))

    global serverURL
    try:
        serverURL = parser.get('Requests', 'serverurl')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Requests', 'serverurl', serverURL)
        except ConfigParser.NoSectionError:
            parser.add_section('Requests')
            parser.set('Requests', 'serverurl', serverURL)
    finally:
        print("Server URL: " + serverURL)

    global iftttKey
    try:
        iftttKey = parser.get('Requests', 'iftttkey')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Requests', 'iftttkey', iftttKey)
        except ConfigParser.NoSectionError:
            parser.add_section('Requests')
            parser.set('Requests', 'iftttkey', iftttKey)
    finally:
        print("IFTTT Key: " + iftttKey)

    global iftttEvent
    try:
        iftttEvent = parser.get('Requests', 'iftttevent')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Requests', 'iftttevent', iftttEvent)
        except ConfigParser.NoSectionError:
            parser.add_section('Requests')
            parser.set('Requests', 'iftttevent', iftttEvent)
    finally:
        print("IFTTT Event: " + iftttEvent)

    global flaskEnabled
    try:
        flaskEnabled = parser.getboolean('RemoteConfig', 'flaskenabled')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('RemoteConfig', 'flaskenabled', str(flaskEnabled))
        except ConfigParser.NoSectionError:
            parser.add_section('RemoteConfig')
            parser.set('RemoteConfig', 'flaskenabled', str(flaskEnabled))
    finally:
        print("Flask Enabled: " + str(flaskEnabled))

    global socketEnabled
    try:
        socketEnabled = parser.getboolean('RemoteConfig', 'socketenabled')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('RemoteConfig', 'socketenabled', str(socketEnabled))
        except ConfigParser.NoSectionError:
            parser.add_section('RemoteConfig')
            parser.set('RemoteConfig', 'socketenabled', str(socketEnabled))
    finally:
        print("Socket Enabled: " + str(socketEnabled))

    global relayAddress
    try:
        relayAddress = parser.get('RemoteConfig', 'relayaddress')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('RemoteConfig', 'relayaddress', relayAddress)
        except ConfigParser.NoSectionError:
            parser.add_section('RemoteConfig')
            parser.set('RemoteConfig', 'relayaddress', relayAddress)
    finally:
        print("Relay Address: " + relayAddress)

    global relayPort
    try:
        relayPort = parser.get('RemoteConfig', 'relayport')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('RemoteConfig', 'relayport', str(relayPort))
        except ConfigParser.NoSectionError:
            parser.add_section('RemoteConfig')
            parser.set('RemoteConfig', 'relayport', str(relayPort))
    finally:
        print("Relay Port: " + str(relayPort))

    global configUsername
    try:
        configUsername = parser.get('RemoteConfig', 'configusername')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('RemoteConfig', 'configusername', configUsername)
        except ConfigParser.NoSectionError:
            parser.add_section('RemoteConfig')
            parser.set('RemoteConfig', 'configusername', configUsername)
    finally:
        print("Config Username: " + configUsername)

    global configPassword
    try:
        configPassword = parser.get('RemoteConfig', 'configpassword')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('RemoteConfig', 'configpassword', configPassword)
        except ConfigParser.NoSectionError:
            parser.add_section('RemoteConfig')
            parser.set('RemoteConfig', 'configpassword', configPassword)
    finally:
        print("Config Password: " + configPassword)

    global magnetEnabled
    try:
        magnetEnabled = parser.getboolean('Magnetometer', 'magnetenabled')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Magnetometer', 'magnetenabled', str(magnetEnabled))
        except ConfigParser.NoSectionError:
            parser.add_section('Magnetometer')
            parser.set('Magnetometer', 'magnetenabled', str(magnetEnabled))
    finally:
        print("Magnet Enabled: " + str(magnetEnabled))

    global magnetInterval
    try:
        magnetInterval = parser.getfloat('Magnetometer', 'magnetinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Magnetometer', 'magnetinterval', str(magnetInterval))
        except ConfigParser.NoSectionError:
            parser.add_section('Magnetometer')
            parser.set('Magnetometer', 'magnetinterval', str(magnetInterval))
    finally:
        print("Magnetometer Interval: " + str(magnetInterval))

    # Write the config file back to disk with the given values and
    # filling in any blanks with the defaults
    write_config()

    print("-------------------------")


def write_config():
    """Writes any changes to the Config Parser memory back to the client.cfg file on disk to save changes.

    Called by config() to create the file if missing and cleanup() to save values for the next execution.
    """
    with open('client.cfg', 'w') as configfile:
        parser.write(configfile)
        os.system("chmod 777 client.cfg")


def setup():
    """Prepares the Client for execution by starting the threads and enabling interrupts.

    Called when the Client is started but should be called directly when using the Client in another project.
    """
    # CPU serial shouldn't change so it is only updated once
    update_serial()

    if get_config_value("hatenabled") == "True":
        if get_config_value("hatused") == "Sensorian":
            sensorian_setup()
        elif get_config_value("hatused") == "Sense HAT":
            sense_hat_setup()

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
    reboot_thread("MagnetThread", magnetInterval, "UpdateMagnetometer")

    flaskEnabledLock.acquire()
    temp_flask_enabled = flaskEnabled
    flaskEnabledLock.release()
    if temp_flask_enabled:
        flask_thread = FlaskThread()
        flask_thread.start()

    if check_sentinel("SocketSentinel"):
        socket_thread = SocketThread()
        socket_thread.start()


def main():
    """The main method. Loops the display of values on the LCD and/or console until told to terminate.

    Called when the Client is started but could be called directly to automate the data displays when imported.
    """
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


def cleanup():
    """Tells all the threads to stop gracefully and performs other final actions like writing the config file.

    Called when the Client is terminated but should be called directly when done using the Client in another project.
    """
    kill_flask()

    if get_config_value("hatenabled") == "True":
        if get_config_value("hatused") == "Sensorian":
            GPIO.cleanup()

    write_config()

    set_sentinel("UpdateDateTime", False)
    set_sentinel("UpdateAmbient", False)
    set_sentinel("UpdateLight", False)
    set_sentinel("UpdateAccelerometer", False)
    set_sentinel("UpdateCPUTemp", False)
    set_sentinel("UpdateWatchedInterfaceIP", False)
    set_sentinel("UpdatePublicIP", False)
    set_sentinel("SendValues", False)
    set_sentinel("UpdateMagnetometer", False)
    set_sentinel("SocketSentinel", False)


# Assuming this program is run itself, execute normally
if __name__ == "__main__":
    # Initialize variables once by reading or creating the config file
    config()
    # Run the main method, halting on keyboard interrupt if run from console
    try:
        setup()
        main()
    except KeyboardInterrupt:
        print("...Quitting ...")
    # Tell all threads to stop if the main program stops by setting their
    # respective repeat sentinels to False
    finally:
        cleanup()
