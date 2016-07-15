# SensorianHubClient
Python client for the Sensorian Shield on Raspberry Pi to display and POST data  
Compatible with the latest official Raspbian image (2016-05-27) and Python 2.7  
Previous versions may be compatible but are currently untested  

Code written and maintained myself with the use of the Sensorian Shield firmware  
Please see Sensorian on [GitHub](https://github.com/sensorian) or their [main website](http://sensorian.io/) for details  
Currently written in Python with the use of Python and C drivers/DLLs  

To get this working in a split, just follow these simple instructions!  
To summarize for experts, simply clone/download the repo wherever and run the install script!  

1. Install the latest Raspbian image to your Pi following [this official guide](https://www.raspberrypi.org/documentation/installation/installing-images/)  
2. Boot up the Pi, and connect to it however you like. A display cable is not necessary.  
3. Run `sudo raspi-config` to your liking, remember that you can simply boot to console, no display required.  
4. Be sure to enable the SPI and I2C interfaces in Advanced Options, and optionally SSH.   
5. Download/clone the project to a directory by navigating to it and typing the following line  
  * `git clone https://github.com/sensorian/SensorianHubClient.git` 
  * Or if you're feeling adventurous and want to run what is likely my broken development code, try this:  
  * `git clone https://github.com/sensorian/SensorianHubClient.git -b development --single-branch`
6. Change into the new directory using `cd SensorianHubClient` then type `chmod +x install.sh`  
7. Run `./install.sh` and wait for it to finish  
8. When it is finally done installing dependencies, reboot the Pi with `sudo reboot`  
9. Finally, `sudo python Sensorian_Client.py` to run the client!  

It works best when run automatically on every boot, so add it to cron to do so!  
For the uninitiated, here's how:  

1. Type `sudo crontab -e` and select option 2  
2. Scroll down to the bottom of the file using the arrow keys  
3. Paste the following line at the bottom, changing the path if you installed the project elsewhere  
  * `@reboot cd /home/pi/SensorianHubClient && python ./Sensorian_Client.py`  
4. Press Ctrl+X to exit the file, pressing Y and Enter to save changes  
5. Finally reboot the Pi again using `sudo reboot` and it should run automatically!  

The Client can also be imported into your own code!  
To see examples of this, check out and try running the included code examples.  
1. `Example_Lights.py` - Adjusts the brightness of a Philips Hue lightbulb to maintain a certain light level  
  * This could be used to turn up your lights as the sun goes down in a windowed room  
2. `Example_Door.py` - Triggers an IFTTT recipe when a door is opened using a magnet on the door frame  
  * Mount the Pi to the door or frame and the magnet on the other and it will sense when the magnet moves away  

To add it to your own code, follow these simple steps.  
1. At the top have `import Sensorian_Client`  
2. Run `Sensorian_Client.config()` to get values from your `client.cfg` config file or defaults  
3. Run `Sensorian_Client.setup()` to start the Client with your set configuration  
Now the Client will be running in the background, collecting data you requested at your intervals.  
You can call any of the getters to find the last polled value, ie. `.get_light()` or `.get_ambient_temp()`  
You can call other functions like `.ifttt_trigger()` or `.shutdown_pi()` to access their functionality too  

Options can be configured in the client.cfg config file included  
If you mess it up or accidently delete it, the program will recreate it with default values  
Most options can also be changed in the local config menu using the capacitive buttons and TFT LCD screen  
On top of that, if Flask is enabled, the program can be remotely configured through HTTP requests  
If you can't access your Client from outside its network, try out the included relay.  
This requires running the `FlaskServer.py` script located in the [SensorianHubSite](https://github.com/sensorian/SensorianHubSite) repo  

Hope you find it useful, feel free to contribute or tell me things you'd like to see!