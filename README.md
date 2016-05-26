# SensorianHubClient
Python client for the Sensorian Shield on Raspberry Pi to display and POST data  
Course project for SOFE 4870U - Special Topics: Cloud Computing 2016  

Code written and maintained myself with the use of the Sensorian Shield firmware  
Please see Sensorian on [GitHub](https://github.com/sensorian) or their [main website](http://sensorian.io/) for details  
Currently written in Python with the use of Python and C drivers  
I might port it to C in the future to avoid the use of the DLLs  

To get this working in a split, just follow these simple instructions!  
To summarize for experts, simply clone/download the repo wherever and run the install script!  

1. Install the latest Raspbian image to your Pi following [this official guide](https://www.raspberrypi.org/documentation/installation/installing-images/)  
2. Boot up the Pi, and connect to it however you like. A display cable is not necessary.  
3. Run raspi-config to your liking, remember that you can simply boot to console, no display required.  
4. Be sure to enable the SPI and I2C interfaces in Advanced Options, and optionally SSH.   
5. Download/clone the project to a directory by navigating to it and typing `git clone https://github.com/Gunsmithy/SensorianHubClient.git`  
6. Change into the new directory using `cd SensorianHubClient` then type `chmod +x install.sh`  
7. Run `./install.sh` and wait for it to finish  
8. When it is finally done installing dependencies, reboot the Pi with `sudo reboot`  
9. Finally, `sudo python Sensorian_Client.py` to run the client!  

It works best when run automatically on every boot, so add it to cron to do so!  
For the uninitiated, here's how:  

1. Type `sudo crontab -e` and select option 2  
2. Scroll down to the bottom of the file using the arrow keys  
3. Paste the following line at the bottom, changing the path if you installed the project elsewhere  
..* `@reboot cd /home/pi/SensorianHubClient && python ./Sensorian_Client.py`  
4. Press Ctrl+X to exit the file, pressing Y and Enter to save changes  
5. Finally reboot the Pi again using `sudo reboot` and it should run automatically!  

Options can be configured in the client.cfg config file included  
If you mess it up or accidently delete it, the program will recreate it with default values  
Most options can also be changed in the local config menu using the capacitive buttons and TFT LCD screen  

Hope you find it useful, feel free to contribute or tell me things you'd like to see!