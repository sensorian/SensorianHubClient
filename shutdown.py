#!/usr/bin/python

import sys
import getopt
import os
import time


def main(argv):
    wait_time = 5
    power = False
    reboot = False
    try:
        opts, args = getopt.getopt(argv, "hr", ["time="])
    except getopt.GetoptError:
        print('Usage - shutdown.py -h -r --time=<seconds>')
        sys.exit(2)
	print args
    for opt, arg in opts:
        if opt == '-h':
            power = True
        elif opt == '-r':
            reboot = True
        elif opt == "--time":
            try:
                wait_time = float(arg)
            except TypeError:
                wait_time = 6
            except ValueError:
                wait_time = 7
    if reboot:
        print("Rebooting in " + str(wait_time) + " seconds")
        time.sleep(wait_time)
        os.system("sudo shutdown -r now")
    elif power:
        print("Shutting down in " + str(wait_time) + " seconds")
        time.sleep(wait_time)
        os.system("sudo shutdown -h now")
    else:
        print("Neither power off or reboot specified, exiting")

if __name__ == "__main__":
    main(sys.argv[1:])
