#Install other packages from the Raspbian Repository
sudo apt-get -y install i2c-tools || { echo "Failed to install i2c-tools" && exit; }
sudo apt-get -y install libi2c-dev || { echo "Failed to install libi2c-dev" && exit; }
sudo apt-get -y install python-smbus || { echo  "Failed to install python-smbus" && exit; }
sudo apt-get -y install python-numpy || { echo "Failed to install python-numpy" && exit; }
sudo apt-get -y install python-pil || { echo "Failed to install python-imaging" && exit; }
sudo apt-get -y install python-pkg-resources || { echo "Failed to install python-pkg-resources" && exit; }
sudo apt-get -y install python-pip || { echo "Failed to install python-pip" && exit; }
sudo apt-get -y install python-wtforms || { echo "Failed to install python-wtforms" && exit; }

#Compile all needed .so files
#Enter PythonSharedObjectSrc
cd PythonSharedObjectSrc

cd MPL3115A2
make
cd ..

cd FXOS8700CQR1
make
cd ..

cd CAP1203
make
cd ..

#Leave PythonSharedObjectSrc
cd ..

#Copy the files into where they are needed
cp -p PythonSharedObjectSrc/MPL3115A2/libMPL.so ./libMPL.so

cp -p PythonSharedObjectSrc/FXOS8700CQR1/libFXO.so ./libFXO.so

cp -p PythonSharedObjectSrc/CAP1203/libCAP.so ./libCAP.so

#At this point, everything should be installed.
echo "Sensorian Client dependencies should now be setup. Please reboot!"