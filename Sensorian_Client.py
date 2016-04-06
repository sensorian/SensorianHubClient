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

#Sensor initializations

#RTC excepts on first call on boot
RTCNotReady = True
while (RTCNotReady):
    try:
        RTC = rtc.MCP79410()
        RTCNotReady = False
    except:
        RTCNotReady = True

#LightSensor needs C drivers to turn on
#Currently just part of a cron job, might include here
    
imuSensor = imuSens.FXOS8700CQR1()
imuSensor.configureAccelerometer()
imuSensor.configureMagnetometer()
imuSensor.configureOrientation()
AltiBar = altibar.MPL3115A2()
AltiBar.ActiveMode()
AltiBar.BarometerMode()
print "Giving the Barometer 2 seconds"
time.sleep(2)
CapTouch = touch.CAP1203()

disp = GLCD.TFT()		# Create TFT LCD display class.
disp.initialize()		# Initialize display.
disp.clear()			# Alternatively can clear to a black screen by calling:
canvas = Image.new("RGB",(128,160))
#draw = disp.draw()		# Get a PIL Draw object to start drawing on the display buffer
font = ImageFont.truetype('/usr/share/fonts/truetype/freefont/FreeSansBold.ttf', 14)    # use a truetype font

#Thread sentinels
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

#Global sensor/IP variables protected by locks below
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
button = 0
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

#Lock to ensure one sensor used at a time
I2CLock = threading.Lock()

#Sentinel Thread Locks
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

#Global Variable Thread Locks
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

def UpdateSerial():
    # Extract serial from cpuinfo file
    global cpuSerial
    tempSerial = "0000000000000000"
    try:
        f = open('/proc/cpuinfo','r')
        for line in f:
          if line[0:6]=='Serial':
              tempSerial = line[10:26]
        f.close()
    except:
        tempSerial = "ERROR000000000"
    finally:
        serialLock.acquire()
        cpuSerial = tempSerial
        serialLock.release()

def GetSerial():
    serialLock.acquire()
    tempSerial = cpuSerial
    serialLock.release()
    return tempSerial

class GeneralThread (threading.Thread):
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
        while (self.repeat):
            methods[self.method]()
            self.slept = 0
            while (self.slept < self.interval):
                self.repeat = CheckSentinel(self.method)
                if (self.repeat == False):
                    print "Killing " + self.name
                    break
                if (self.interval - self.slept < 1):
                    self.toSleep = self.interval - self.slept
                else:
                    self.toSleep = 1
                time.sleep(self.toSleep)
                self.slept = self.slept + self.toSleep

def UpdateLight():
    global light
    tempLight = -1
    I2CLock.acquire()
    try:
        AmbientLight = LuxSens.APDS9300()
        channel1 = AmbientLight.readChannel(1)
        channel2 = AmbientLight.readChannel(0)
        tempLight = AmbientLight.getLuxLevel(channel1,channel2)
    except:
        print "EXCEPTION IN LIGHT UPDATE"
    I2CLock.release()
    lightLock.acquire()
    try:
        light = tempLight
    finally:
        lightLock.release()
        
def GetLight():
    lightLock.acquire()
    try:
        tempLight = light
    finally:
        lightLock.release()
    return tempLight

def GetAmbientTemp():
    ambientTempLock.acquire()
    returnTemp = ambientTemp
    ambientTempLock.release()
    return returnTemp

def GetAmbientPressure():
    ambientPressureLock.acquire()
    returnPress = float(ambientPressure)/1000
    ambientPressureLock.release()
    return returnPress

def UpdateAmbient():
    global ambientTemp
    global ambientPressure
    time.sleep(0.5)
    I2CLock.acquire()
    temp = AltiBar.ReadTemperature()
    I2CLock.release()
    time.sleep(0.5)
    ambientTempLock.acquire()
    ambientTemp = temp
    ambientTempLock.release()
    pressureEnabledLock.acquire()
    tempEnabled = pressureEnabled
    pressureEnabledLock.release()
    if (tempEnabled):
        I2CLock.acquire()
        press = AltiBar.ReadBarometricPressure()
        I2CLock.release()
        ambientPressureLock.acquire()
        ambientPressure = press
        ambientPressureLock.release()
    else:
        print "NoPressureNeeded"
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

def UpdateDateTime():
    global currentDateTime
    I2CLock.acquire()
    tempDateTime = RTC.GetTime()
    I2CLock.release()
    rtcLock.acquire()
    currentDateTime = tempDateTime
    rtcLock.release()

def GetDateTime():
    rtcLock.acquire()
    tempDateTime = currentDateTime
    rtcLock.release()
    return tempDateTime

def UpdateCPUTemp():
    global cpuTemp
    tPath = '/sys/class/thermal/thermal_zone0/temp'
    tFile = open(tPath)
    cpu = tFile.read()
    tFile.close()
    temp = (float(cpu)/1000)
    cpuTempLock.acquire()
    cpuTemp = temp
    cpuTempLock.release()

def GetCPUTemp():
    cpuTempLock.acquire()
    temp = cpuTemp
    cpuTempLock.release()
    return temp

def UpdateWatchedInterfaceIP():
    global interfaceIP
    interfaceLock.acquire()
    tempInterface = watchedInterface
    interfaceLock.release()
    ipaddr = GetInterfaceIP(tempInterface)
    interfaceIPLock.acquire()
    interfaceIP = ipaddr
    interfaceIPLock.release()

def GetWatchedInterfaceIP():
    interfaceIPLock.acquire()
    tempIP = interfaceIP
    interfaceIPLock.release()
    return tempIP

def GetInterfaceIP(interface):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        ipaddr = socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', interface[:15])
    )[20:24])
    except Exception:
        ipaddr = socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', 'lo'[:15])
    )[20:24])
    return ipaddr

def UpdatePublicIP():
    global publicIP
    proc = subprocess.Popen(["curl", "-s", "-4", "icanhazip.com"], stdout=subprocess.PIPE)
    (out, err) = proc.communicate()
    publicIPLock.acquire()
    publicIP = out.rstrip()
    publicIPLock.release()

def GetPublicIP():
    publicIPLock.acquire()
    tempIP = publicIP
    publicIPLock.release()
    return tempIP

def UpdateAccelerometer():
    global mode
    global modeprevious
    global accelX
    global accelY
    global accelZ
    I2CLock.acquire()
    if(imuSensor.readStatusReg() & 0x80):
        x,y,z = imuSensor.pollAccelerometer()
        orienta = imuSensor.getOrientation()
        I2CLock.release()
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
            #alert change in orientation
            #print "Changed orientation"
            modeprevious = mode

def GetMode():
    modeLock.acquire()
    tempMode = mode
    modeLock.release()
    return tempMode

def GetAccelX():
    accelXLock.acquire()
    x = accelX
    accelXLock.release()
    return x

def GetAccelY():
    accelYLock.acquire()
    y = accelY
    accelYLock.release()
    return y

def GetAccelZ():
    accelZLock.acquire()
    z = accelZ
    accelZLock.release()
    return z

def UpdateButton():
    global button
    I2CLock.acquire()
    tempButton = CapTouch.readPressedButton()
    I2CLock.release()
    buttonLock.acquire()
    button = tempButton
    buttonLock.release()

def GetButton():
    buttonLock.acquire()
    tempButton = button
    buttonLock.release()
    return tempButton

def CheckSentinel(sentinel):
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

def DisplayValues():
    #print "Landscape left. \r\n"
    #image = image1.rotate(90).resize((128, 160))
    #graphicDisplay.display(image)
    disp.clear()
    if (lockOrientation == False):
        orientation = GetMode()
    else:
        orientation = defaultOrientation
    if (orientation == 0):
        textDraw = Image.new('RGB',(160,128))
        angle = 90
    elif (orientation == 1):
        textDraw = Image.new('RGB',(160,128))
        angle = 270
    elif (orientation == 2):
        textDraw = Image.new('RGB',(128,160))
        angle = 180
    elif (orientation == 3):
        textDraw = Image.new('RGB',(128,160))
        angle = 0
    else:
        textDraw = Image.new('RGB',(128,160))
        angle = 90
    
    textDraw2 = ImageDraw.Draw(textDraw)
    textDraw2.text((0, 0), "HW: " + GetSerial(), font=font)
    rtcTime = GetDateTime()
    dat = "Date: " + str(rtcTime.date) + "/" + str(rtcTime.month)+ "/" + str(rtcTime.year)  	#convert to string and print it
    textDraw2.text((0, 12), dat, font=font)
    tmr = "Time: " + '{:02d}'.format(rtcTime.hour) + ":" + '{:02d}'.format(rtcTime.min)+ ":" + '{:02d}'.format(rtcTime.sec)  	#convert to string and print it
    textDraw2.text((0, 24), tmr, font=font)
    textDraw2.text((0, 36), "Light: " + str(GetLight()) + " lx", font=font)
    textDraw2.text((0, 48), "Temp: " + str(GetAmbientTemp()) + " C", font=font)
    textDraw2.text((0, 60), "Press: " + str(GetAmbientPressure()) + " kPa", font=font)
    textDraw2.text((0, 72), "CPU Temp: " + str(GetCPUTemp()) + " C", font=font)
    textDraw2.text((0, 84), "LAN IP: " + str(GetWatchedInterfaceIP()), font=font)
    textDraw2.text((0, 96), "WAN IP: " + str(GetPublicIP()), font=font)
    #textDraw2.text((0, 108), "Button Pressed: " + str(GetButton()), font=font)
    textDraw2.text((0, 108), "X: " + str(GetAccelX()) + " Y: " + str(GetAccelY()) + " Z: " + str(GetAccelZ()), font=font)
    
    textDraw3 = textDraw.rotate(angle)
    canvas.paste(textDraw3,(0,0))
    disp.display(canvas)

def PrintValues():
    options = {-1 : "Not Ready",
               0 : "Landscape Left",
               1 : "Landscape Right",
               2 : "Portrait Up",
               3 : "Portrait Down"
               }
    rtcTime = GetDateTime()
    print "HW: " + GetSerial()
    print "Date: " + str(rtcTime.date) + "/" + str(rtcTime.month)+ "/" + str(rtcTime.year)  	#convert to string and print it
    print "Time: " + '{:02d}'.format(rtcTime.hour) + ":" + '{:02d}'.format(rtcTime.min)+ ":" + '{:02d}'.format(rtcTime.sec)
    print "Light: " + str(GetLight()) + " lx"
    print "Temp: " + str(GetAmbientTemp()) + " C"
    print "Pressure: " + str(GetAmbientPressure()) + " kPa"
    print "CPU Temp: " + str(GetCPUTemp()) + " C"
    print "LAN IP: " + str(GetWatchedInterfaceIP())
    print "WAN IP: " + GetPublicIP()
    print "Mode: " + options[GetMode()]
    print "Button Pressed: " + str(GetButton())
    print "--------------------"
    
def SendValues():
    rtcTime = GetDateTime()
    TS = "20" + '{:02d}'.format(rtcTime.year) + "-" + '{:02d}'.format(rtcTime.month) + "-" + '{:02d}'.format(rtcTime.date) + " " + '{:02d}'.format(rtcTime.hour) + ":" + '{:02d}'.format(rtcTime.min)+ ":" + '{:02d}'.format(rtcTime.sec)
    #print "TS: " + TS
    url = 'http://sensorianhub.azurewebsites.net/insertData.php'
    payload = {'HW': str(GetSerial()),
               'TS': TS,
               'IP': str(GetWatchedInterfaceIP()),
               'CPU': str(GetCPUTemp()), #RED
               'LUX': str(GetLight()), #YELLOW
               'Temp': str(GetAmbientTemp()), #GREEN
               'Press': str(GetAmbientPressure()),#BLUE
               'X': str(float(GetAccelX()/1000)),
               'Y': str(float(GetAccelY()/1000)),
               'Z': str(float(GetAccelZ()/1000))
               }
    try:
        r = requests.post(url, data=json.dumps(payload), timeout=postTimeout)
        print r.text
    except:
        print "POST ERROR"

methods = {"UpdateDateTime" : UpdateDateTime,
           "UpdateAmbient" : UpdateAmbient,
           "UpdateLight" : UpdateLight,
           "UpdateCPUTemp" : UpdateCPUTemp,
           "UpdateWatchedInterfaceIP" : UpdateWatchedInterfaceIP,
           "UpdatePublicIP" : UpdatePublicIP,
           "UpdateAccelerometer" : UpdateAccelerometer,
           "UpdateButton" : UpdateButton,
           "SendValues" : SendValues
           }

def Config():
    print "-------------------------"
    print "Configuring Settings"
    
    parser = ConfigParser.SafeConfigParser()

    parser.read('client.cfg')

    global defaultOrientation
    try:
        defaultOrientation = parser.getint('UI','defaultorientation')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('UI','defaultorientation',str(defaultOrientation))
        except(ConfigParser.NoSectionError):
            parser.add_section('UI')
            parser.set('UI','defaultorientation',str(defaultOrientation))
    finally:
        print "Default Orientation: " + str(defaultOrientation)

    global lockOrientation
    try:
        lockOrientation = parser.getboolean('UI','lockorientation')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('UI','lockorientation',str(lockOrientation))
        except(ConfigParser.NoSectionError):
            parser.add_section('UI')
            parser.set('UI','lockorientation',str(lockOrientation))
    finally:
        print "Lock Orientation: " + str(lockOrientation)
    
    global sleepTime
    try:
        sleepTime = parser.getfloat('UI','refreshinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('UI','refreshinterval',str(sleepTime))
        except(ConfigParser.NoSectionError):
            parser.add_section('UI')
            parser.set('UI','refreshinterval',str(sleepTime))
    finally:        
        print "Refresh Interval: " + str(sleepTime)

    global watchedInterface
    try:
        watchedInterface = parser.get('General','watchedinterface')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('General','watchedinterface',watchedInterface)
        except(ConfigParser.NoSectionError):
            parser.add_section('General')
            parser.set('General','watchedinterface',watchedInterface)
    finally:
        print "Watched Interface: " + watchedInterface

    global postInterval
    try:
        postInterval = parser.getfloat('Requests','postinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Requests','postinterval',str(postInterval))
        except(ConfigParser.NoSectionError):
            parser.add_section('Requests')
            parser.set('Requests','postinterval',str(postInterval))
    finally:
        print "POST Interval: " + str(postInterval)

    global postTimeout
    try:
        postTimeout = parser.getfloat('Requests','posttimeout')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Requests','posttimeout',str(postTimeout))
        except(ConfigParser.NoSectionError):
            parser.add_section('Requests')
            parser.set('Requests','posttimeout',str(postTimeout))
    finally:
        print "POST Timeout: " + str(postTimeout)

    global ambientInterval
    try:
        ambientInterval = parser.getfloat('Ambient','ambientinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Ambient','ambientinterval',str(ambientInterval))
        except(ConfigParser.NoSectionError):
            parser.add_section('Ambient')
            parser.set('Ambient','ambientinterval',str(ambientInterval))
    finally:
        print "Ambient Interval: " + str(ambientInterval)
    
    global lightInterval
    try:
        lightInterval = parser.getfloat('Light','lightinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Light','lightinterval',str(lightInterval))
        except(ConfigParser.NoSectionError):
            parser.add_section('Light')
            parser.set('Light','lightinterval',str(lightInterval))
    finally:
        print "Light Interval: " + str(lightInterval)

    global cpuTempInterval
    try:
        cpuTempInterval = parser.getfloat('General','cputempinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('General','cputempinterval',str(cpuTempInterval))
        except(ConfigParser.NoSectionError):
            parser.add_section('General')
            parser.set('General','cputempinterval',str(cpuTempInterval))
    finally:
        print "CPU Temp Interval: " + str(cpuTempInterval)

    global interfaceInterval
    try:
        interfaceInterval = parser.getfloat('General','interfaceinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('General','interfaceinterval',str(interfaceInterval))
        except(ConfigParser.NoSectionError):
            parser.add_section('General')
            parser.set('General','interfaceinterval',str(interfaceInterval))
    finally:
        print "Local IP Interval: " + str(interfaceInterval)

    global publicInterval
    try:
        publicInterval = parser.getfloat('General','publicinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('General','publicinterval',str(publicInterval))
        except(ConfigParser.NoSectionError):
            parser.add_section('General')
            parser.set('General','publicinterval',str(publicInterval))
    finally:
        print "Public IP Interval: " + str(publicInterval)

    global accelInterval
    try:
        accelInterval = parser.getfloat('Accelerometer','accelinterval')
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError, ValueError):
        try:
            parser.set('Accelerometer','accelinterval',str(accelInterval))
        except(ConfigParser.NoSectionError):
            parser.add_section('Accelerometer')
            parser.set('Accelerometer','accelinterval',str(accelInterval))
    finally:
        print "Accelerometer Interval: " + str(accelInterval)
        
    with open('client.cfg', 'w') as configfile:
        parser.write(configfile)
        os.system("chmod 777 client.cfg")

    print "-------------------------"

def main():

    UpdateSerial()

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

    buttonThread = GeneralThread(7, "ButtonThread", 1, "UpdateButton")
    buttonThread.start()

    requestThread = GeneralThread(8, "SendThread", postInterval, "SendValues")
    requestThread.start()

    #time.sleep(5)
    #SendValues()

    while True:
        #PrintValues()
        DisplayValues()
        time.sleep(sleepTime)
 
if __name__=="__main__":
    Config()
    try:
        main()
    except KeyboardInterrupt:
        print("...Quitting ...")
    finally:
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
