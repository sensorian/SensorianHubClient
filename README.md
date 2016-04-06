# SensorianHubClient
Python client for the Sensorian Shield on Raspberry Pi to display and POST data  
Course project for SOFE 4870U - Special Topics: Cloud Computing 2016  

Code written and maintained myself with the use of the Sensorian Shield firmware  
Please see Sensorian on [GitHub](https://github.com/sensorian) or their [main website](http://sensorian.io/) for details  
Currently written in Python with the use of Python and C drivers  
Might port to C in the future to avoid the use of the DLLs  

To summarize, simply clone/download the repo to a location of your choice and run the install script  
1. Download/clone to a directory  
2. From the directory, run chmod +x install.sh  
3. Run ./install.sh and wait for it to finish  
4. When it is done, reboot the Pi  
5. Finally, sudo python Sensorian_Client.py to run the client!  

Options can be configured in the client.cfg config file included  
If you mess it up or accidently delete it, the program will recreate it with default values  

Hope you find it useful, feel free to contribute or tell me things you'd like to see!