#!/usr/bin/python
import ConfigParser
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
sendEnabled = True

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
watchedInterface = "wlan0"
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
menuPosition = 0
parser = ConfigParser.SafeConfigParser()

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
                    print "Killing " + self.name
                    break
                # If it did not, sleep for another second unless less than a
                # second needs to pass to reach the end of the current loop
                if (self.interval - self.slept < 1):
                    self.toSleep = self.interval - self.slept
                else:
                    self.toSleep = 1
                time.sleep(self.toSleep)
                self.slept = self.slept + self.toSleep


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
        print "EXCEPTION IN LIGHT UPDATE"
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
    returnPress = float(ambientPressure) / 1000
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
        print "NoPressureNeeded"
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
    temp = (float(cpu) / 1000)
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
            modeprevious = mode


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
    print "You Shouldn't Be Here..."


# Update the button pressed when interrupted
def ButtonEventHandler(pin):
    global button
    I2CLock.acquire()
    tempNewButton = CapTouch.readPressedButton()
    I2CLock.release()
    buttonLock.acquire()
    button = tempNewButton
    buttonLock.release()
    if (tempNewButton != 0):
        ButtonHandler(tempNewButton)


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
        print "Display Pressed " + str(pressed)
        if (pressed == 2):
            inMenuLock.acquire()
            inMenu = True
            inMenuLock.release()
            currentMenuLock.acquire()
            currentMenu = "Top"
            currentMenuLock.release()
            menuElementsLock.acquire()
            menuElements = ["Exit", "General", "UI", "Requests", "Accelerometer", "Light", "Ambient"]
            menuElementsLock.release()
            menuPositionLock.acquire()
            menuPosition = 0
            menuPositionLock.release()
    else:
        print "Menu Pressed " + str(pressed)
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
            if (tempMenuPos != 0):
                menuPositionLock.acquire()
                menuPosition = tempMenuPos - 1
                menuPositionLock.release()
        elif (pressed == 3):
            if (tempMenuPos != tempLength - 1):
                menuPositionLock.acquire()
                menuPosition = tempMenuPos + 1
                menuPositionLock.release()
        elif (pressed == 2):
            if (tempMenu == "Top"):
                if (tempElements[tempMenuPos] == "Exit"):
                    inMenuLock.acquire()
                    inMenu = False
                    inMenuLock.release()
                elif (tempElements[tempMenuPos] == "General"):
                    currentMenuLock.acquire()
                    currentMenu = "General"
                    currentMenuLock.release()
                    menuElementsLock.acquire()
                    menuElements = ["Watched Interface", "CPU Temp Interval", "Interface Interval", "Public Interval"]
                    menuElementsLock.release()
                    menuPositionLock.acquire()
                    menuPosition = 0
                    menuPositionLock.release()
            elif (tempMenu == "General"):
                if (tempElements[tempMenuPos] == "Watched Interface"):
                    currentMenuLock.acquire()
                    currentMenu = "Watched Interface"
                    currentMenuLock.release()
                    proc = subprocess.Popen(["ls", "-1", "/sys/class/net"], stdout=subprocess.PIPE)
                    (out, err) = proc.communicate()
                    interfaces = out.rstrip()
                    interfacesList = interfaces.split()
                    menuElementsLock.acquire()
                    menuElements = interfacesList
                    menuElementsLock.release()
                    menuPositionLock.acquire()
                    menuPosition = 0
                    menuPositionLock.release()
            elif (tempMenu == "Watched Interface"):
                global watchedInterface
                newInterface = tempElements[tempMenuPos]
                interfaceLock.acquire()
                watchedInterface = newInterface
                interfaceLock.release()
                parser.set('General', 'watchedinterface', newInterface)
                UpdateWatchedInterfaceIP()
                inMenuLock.acquire()
                inMenu = False
                inMenuLock.release()


# Displays all the watched variables on the TFT LCD if enabled
def DisplayValues():
    disp.clear()
    # Checks if the orientation of the display should be locked
    # If so, force the default orientation from the config file
    if (lockOrientation == False):
        orientation = GetMode()
    else:
        orientation = defaultOrientation
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
        for x in range(0,9):
            try:
                textDraw2.text((18, x*12), tempElements[x], font=font)
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
    print "HW: " + GetSerial()
    print "Date: " + str(rtcTime.date) + "/" + str(rtcTime.month) + "/" + str(
        rtcTime.year)  # convert to string and print it
    print "Time: " + '{:02d}'.format(rtcTime.hour) + ":" + '{:02d}'.format(rtcTime.min) + ":" + '{:02d}'.format(
        rtcTime.sec)
    print "Light: " + str(GetLight()) + " lx"
    print "Temp: " + str(GetAmbientTemp()) + " C"
    print "Pressure: " + str(GetAmbientPressure()) + " kPa"
    print "CPU Temp: " + str(GetCPUTemp()) + " C"
    print "LAN IP: " + str(GetWatchedInterfaceIP())
    print "WAN IP: " + GetPublicIP()
    print "Mode: " + options[GetMode()]
    print "Button Pressed: " + str(GetButton())
    print "--------------------"


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
               'X': str(GetAccelX() / 1000.0),
               'Y': str(GetAccelY() / 1000.0),
               'Z': str(GetAccelZ() / 1000.0)
               }
    # Attempt to POST the JSON to the given URL, catching any failures
    try:
        r = requests.post(serverURL, data=json.dumps(payload), timeout=postTimeout)
        # print r.text #For debugging POST requests
    except:
        print "POST ERROR - Check connection and server"


# Method names for the threads to call to update their variables
methods = {"UpdateDateTime": UpdateDateTime,
           "UpdateAmbient": UpdateAmbient,
           "UpdateLight": UpdateLight,
           "UpdateCPUTemp": UpdateCPUTemp,
           "UpdateWatchedInterfaceIP": UpdateWatchedInterfaceIP,
           "UpdatePublicIP": UpdatePublicIP,
           "UpdateAccelerometer": UpdateAccelerometer,
           "UpdateButton": UpdateButton,
           "SendValues": SendValues
           }


# Method to read the config file or set defaults if parameters missing
def Config():
    print "-------------------------"
    print "Configuring Settings"
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
        except(ConfigParser.NoSectionError):
            parser.add_section('UI')
            parser.set('UI', 'defaultorientation', str(defaultOrientation))
    finally:
        print "Default Orientation: " + str(defaultOrientation)

    global lockOrientation
    try:
        lockOrientation = parser.getboolean('UI', 'lockorientation')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('UI', 'lockorientation', str(lockOrientation))
        except(ConfigParser.NoSectionError):
            parser.add_section('UI')
            parser.set('UI', 'lockorientation', str(lockOrientation))
    finally:
        print "Lock Orientation: " + str(lockOrientation)

    global sleepTime
    try:
        sleepTime = parser.getfloat('UI', 'refreshinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('UI', 'refreshinterval', str(sleepTime))
        except(ConfigParser.NoSectionError):
            parser.add_section('UI')
            parser.set('UI', 'refreshinterval', str(sleepTime))
    finally:
        print "Refresh Interval: " + str(sleepTime)

    global watchedInterface
    try:
        watchedInterface = parser.get('General', 'watchedinterface')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('General', 'watchedinterface', watchedInterface)
        except(ConfigParser.NoSectionError):
            parser.add_section('General')
            parser.set('General', 'watchedinterface', watchedInterface)
    finally:
        print "Watched Interface: " + watchedInterface

    global postInterval
    try:
        postInterval = parser.getfloat('Requests', 'postinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Requests', 'postinterval', str(postInterval))
        except(ConfigParser.NoSectionError):
            parser.add_section('Requests')
            parser.set('Requests', 'postinterval', str(postInterval))
    finally:
        print "POST Interval: " + str(postInterval)

    global postTimeout
    try:
        postTimeout = parser.getfloat('Requests', 'posttimeout')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Requests', 'posttimeout', str(postTimeout))
        except(ConfigParser.NoSectionError):
            parser.add_section('Requests')
            parser.set('Requests', 'posttimeout', str(postTimeout))
    finally:
        print "POST Timeout: " + str(postTimeout)

    global ambientInterval
    try:
        ambientInterval = parser.getfloat('Ambient', 'ambientinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Ambient', 'ambientinterval', str(ambientInterval))
        except(ConfigParser.NoSectionError):
            parser.add_section('Ambient')
            parser.set('Ambient', 'ambientinterval', str(ambientInterval))
    finally:
        print "Ambient Interval: " + str(ambientInterval)

    global lightInterval
    try:
        lightInterval = parser.getfloat('Light', 'lightinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Light', 'lightinterval', str(lightInterval))
        except(ConfigParser.NoSectionError):
            parser.add_section('Light')
            parser.set('Light', 'lightinterval', str(lightInterval))
    finally:
        print "Light Interval: " + str(lightInterval)

    global cpuTempInterval
    try:
        cpuTempInterval = parser.getfloat('General', 'cputempinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('General', 'cputempinterval', str(cpuTempInterval))
        except(ConfigParser.NoSectionError):
            parser.add_section('General')
            parser.set('General', 'cputempinterval', str(cpuTempInterval))
    finally:
        print "CPU Temp Interval: " + str(cpuTempInterval)

    global interfaceInterval
    try:
        interfaceInterval = parser.getfloat('General', 'interfaceinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('General', 'interfaceinterval', str(interfaceInterval))
        except(ConfigParser.NoSectionError):
            parser.add_section('General')
            parser.set('General', 'interfaceinterval', str(interfaceInterval))
    finally:
        print "Local IP Interval: " + str(interfaceInterval)

    global publicInterval
    try:
        publicInterval = parser.getfloat('General', 'publicinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('General', 'publicinterval', str(publicInterval))
        except(ConfigParser.NoSectionError):
            parser.add_section('General')
            parser.set('General', 'publicinterval', str(publicInterval))
    finally:
        print "Public IP Interval: " + str(publicInterval)

    global accelInterval
    try:
        accelInterval = parser.getfloat('Accelerometer', 'accelinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Accelerometer', 'accelinterval', str(accelInterval))
        except(ConfigParser.NoSectionError):
            parser.add_section('Accelerometer')
            parser.set('Accelerometer', 'accelinterval', str(accelInterval))
    finally:
        print "Accelerometer Interval: " + str(accelInterval)

    global displayEnabled
    try:
        displayEnabled = parser.getboolean('UI', 'displayenabled')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('UI', 'displayenabled', str(displayEnabled))
        except(ConfigParser.NoSectionError):
            parser.add_section('UI')
            parser.set('UI', 'displayenabled', str(displayEnabled))
    finally:
        print "Display Enabled: " + str(displayEnabled)

    global printEnabled
    try:
        printEnabled = parser.getboolean('UI', 'printenabled')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('UI', 'printenabled', str(printEnabled))
        except(ConfigParser.NoSectionError):
            parser.add_section('UI')
            parser.set('UI', 'printenabled', str(printEnabled))
    finally:
        print "Print Enabled: " + str(printEnabled)

    global serverURL
    try:
        serverURL = parser.get('Requests', 'serverurl')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Requests', 'serverurl', serverURL)
        except(ConfigParser.NoSectionError):
            parser.add_section('Requests')
            parser.set('Requests', 'serverurl', serverURL)
    finally:
        print "Server URL: " + serverURL

    global iftttKey
    try:
        iftttKey = parser.get('Requests', 'iftttkey')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Requests', 'iftttkey', iftttKey)
        except(ConfigParser.NoSectionError):
            parser.add_section('Requests')
            parser.set('Requests', 'iftttkey', iftttKey)
    finally:
        print "IFTTT Key: " + iftttKey

    global iftttEvent
    try:
        iftttEvent = parser.get('Requests', 'iftttevent')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Requests', 'iftttevent', iftttEvent)
        except(ConfigParser.NoSectionError):
            parser.add_section('Requests')
            parser.set('Requests', 'iftttevent', iftttEvent)
    finally:
        print "IFTTT Event: " + iftttEvent

    # Write the config file back to disk with the given values and
    # filling in any blanks with the defaults
    with open('client.cfg', 'w') as configfile:
        parser.write(configfile)
        os.system("chmod 777 client.cfg")

    print "-------------------------"


# Main Method
def main():
    # CPU serial shouldn't change so it is only updated once
    UpdateSerial()

    # Create threads and start them to monitor the various sensors and
    # IP variables at their given intervals, 1 second interval for time/buttons
    timeThread = GeneralThread(0, "TimeThread", 1, "UpdateDateTime")
    timeThread.start()

    ambientThread = GeneralThread(1, "AmbientThread", ambientInterval, "UpdateAmbient")
    ambientThread.start()

    lightThread = GeneralThread(2, "LightThread", lightInterval, "UpdateLight")
    lightThread.start()

    cpuThread = GeneralThread(3, "CPUTempThread", cpuTempInterval, "UpdateCPUTemp")
    cpuThread.start()

    interfaceIPThread = GeneralThread(4, "InterfaceIPThread", interfaceInterval, "UpdateWatchedInterfaceIP")
    interfaceIPThread.start()

    publicIPThread = GeneralThread(5, "PublicIPThread", publicInterval, "UpdatePublicIP")
    publicIPThread.start()

    accelThread = GeneralThread(6, "AccelThread", accelInterval, "UpdateAccelerometer")
    accelThread.start()

    #buttonThread = GeneralThread(7, "ButtonThread", 60, "UpdateButton")
    #buttonThread.start()

    requestThread = GeneralThread(8, "SendThread", postInterval, "SendValues")
    requestThread.start()


    GPIO.setup(CAP_PIN, GPIO.IN)
    GPIO.add_event_detect(CAP_PIN, GPIO.FALLING)
    GPIO.add_event_callback(CAP_PIN, ButtonEventHandler)
    CapTouch.clearInterrupt()
    CapTouch.enableInterrupt(0, 0, 0x07)


    # Loop the display and/or printing of variables if desired, waiting between
    # calls for the set or default refresh interval
    while True:
        if (printEnabled):
            PrintValues()
        if (displayEnabled):
            DisplayValues()
        time.sleep(sleepTime)


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
        GPIO.cleanup()

        # Writes any changes to the config file back to disk that may have been made
        # through the local config menu
        with open('client.cfg', 'w') as configfile:
            parser.write(configfile)
            os.system("chmod 777 client.cfg")

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
