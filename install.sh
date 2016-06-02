#Update repos first just in case
sudo apt-get update

#Install other packages from the Raspbian Repository
sudo apt-get -y install i2c-tools || { echo "Failed to install i2c-tools" && exit; }
sudo apt-get -y install libi2c-dev || { echo "Failed to install libi2c-dev" && exit; }
sudo apt-get -y install python-dev || { echo "Failed to install python-dev" && exit; }
sudo apt-get -y install python-smbus || { echo "Failed to install python-smbus" && exit; }
sudo apt-get -y install python-numpy || { echo "Failed to install python-numpy" && exit; }
sudo apt-get -y install libjpeg-dev || { echo "Failed to install libjpeg-dev" && exit; }

#Uninstall Python Imaging Library because it leaks and doesn't play well with Pillow
sudo apt-get -y purge python-pil || { echo "Failed to unins python-pil" && exit; }
sudo apt-get -y purge python3-pil || { echo "Failed to uninstall python3-pil" && exit; }

#Clean up some of the leftovers from pil
sudo apt-get -y autoremove

#Install other required python modules using pip
sudo pip install -r requirements.txt

#Compile all needed .so files
#Enter PythonSharedObjectSrc
cd PythonSharedObjectSrc

#Install Broadcom GPIO driver
cd BCM2835
tar zxvf bcm2835-1.50.tar.gz
cd bcm2835-1.50
./configure
make
sudo make check
sudo make install
cd ..
cd ..

#Compile the pressure sensor driver
cd MPL3115A2
make
cd ..

#Compile the Accelerometer driver
cd FXOS8700CQR1
make
cd ..

#Compile the Capacitive Touch Button driver
cd CAP1203
make
cd ..

#Leave PythonSharedObjectSrc
cd ..

#Copy the driver files to where they are needed
cp -p PythonSharedObjectSrc/MPL3115A2/libMPL.so ./libMPL.so

cp -p PythonSharedObjectSrc/FXOS8700CQR1/libFXO.so ./libFXO.so

cp -p PythonSharedObjectSrc/CAP1203/libCAP.so ./libCAP.so

#At this point, everything should be installed and working after reboot
echo "Sensorian Client dependencies should now be setup. Please reboot!"