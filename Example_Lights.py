#!/usr/bin/env python

"""Example_Lights.py: Demonstrates using the API to adjust a Philips Hue light to maintain a light level"""

import time
import math
import Sensorian_Client

__author__ = "Dylan Kauling"
__maintainer__ = "Dylan Kauling"
__status__ = "Development"

# User defined variables for IFTTT.com/maker Channel API credentials and how long to wait for requests
IFTTT_KEY = "d9ip3mcBoqN1_UkP_SyUWnnmnAJapn7BK4WP-7esu29"  # Your API key provided by IFTTT when connecting a Maker channel
IFTTT_EVENT = "HueBrightness"  # The name of the event you chose for the recipe to dim a Hue light
IFTTT_TIMEOUT = 5  # How long to wait in seconds for commands sent to IFTTT.com before timing out
TOLERANCE = 2.0   # How many times the lux levels per Hue brightness setting should be an acceptable range

# Global variables to store the calibrations
lux_at_max = 0  # The light level when the Hue is set to a max brightness of 100
lux_at_min = 0  # The light level when the Hue is set to a min brightness of 0
lux_diff = 0  # The difference in light level between the Hues brightness settings of 0 and 100
lux_per_bright = 5  # The difference in light level for each change in brightness level by 1
desired_lux = 0  # The desired light level to be matched by the Hue, set when the program is first run
current_setting = 0  # The last known value of brightness for the Hue, based on the last command sent


# Sets up the Sensorian sensors for use and prints the current light level to the screen to test
def setup():
    print("Setting up...")
    Sensorian_Client.config()
    Sensorian_Client.setup()
    global desired_lux
    desired_lux = Sensorian_Client.get_light()  # Sets the desired light level to that of when the program ran
    print("Desired Light: " + str(desired_lux))  # Print the desired light level


# Waits until the brightness changes to ensure the request worked given the current light level and desired direction
def wait_for_change(pre_request_lux, direction="BOTH"):
    tolerance = lux_per_bright * TOLERANCE  # Sensitivity - How much the light should change to be considered different
    slept = 0  # Stores a counter to time out the check for a change in brightness in case the brightness is the same
    while True:  # Loops until the brightness changes or it times out
        current_lux = Sensorian_Client.get_light()  # Get the current light value to check against in a second
        time.sleep(1)  # Waits for a second before checking brightness again to see if there was a change
        post_request_lux = Sensorian_Client.get_light()  # Get the current light value to check for changes
        if (post_request_lux > pre_request_lux + tolerance or post_request_lux > current_lux + tolerance) \
                and (direction == "BOTH" or direction == "UP"):
            print("Brightness went up")
            time.sleep(2)  # Waits 2 seconds before breaking the loop in case the bulb is still changing brightness
            break  # Breaks the loop since a brightness change was detected
        elif (post_request_lux < pre_request_lux - tolerance or post_request_lux < current_lux - tolerance) \
                and (direction == "BOTH" or direction == "DOWN"):
            print("Brightness went down")
            time.sleep(2)  # Waits 2 seconds before breaking the loop in case the bulb is still changing brightness
            break  # Breaks the loop since a brightness change was detected
        if slept >= 20:  # Gives the check 20 seconds to catch rare edge cases where the IFTTT request takes a long time
            print("Timed out, brightness may be the same or similar")
            time.sleep(1)  # Waits a second before breaking the loop in case the bulb is still changing brightness
            break  # Breaks the loop since no brightness change was detected after 30 seconds
        slept += 1  # Increases the counter for how long the brightness has been checked


# Checks light levels when the Philips Hue light is set to maximum and minimum brightness
def calibrate():
    print("Calibrating...")
    pre_request_lux = Sensorian_Client.get_light()  # Gets the current light level before the request
    Sensorian_Client.ifttt_trigger(IFTTT_KEY, IFTTT_EVENT, IFTTT_TIMEOUT, 100)  # Sets the Philips Hue brightness to 100
    wait_for_change(pre_request_lux, "UP")  # Waits until the brightness changes from the request or it times out
    global lux_at_max
    lux_at_max = Sensorian_Client.get_light()  # Stores the light value when the Philips Hue is set to max

    pre_request_lux = Sensorian_Client.get_light()  # Gets the current light level before the request
    Sensorian_Client.ifttt_trigger(IFTTT_KEY, IFTTT_EVENT, IFTTT_TIMEOUT, 0)  # Sets the Philips Hue brightness to 0
    wait_for_change(pre_request_lux, "DOWN")  # Waits until the brightness changes from the request or it times out
    global lux_at_min
    lux_at_min = Sensorian_Client.get_light()  # Stores the light value when the Philips Hue is set to min

    global lux_diff
    lux_diff = lux_at_max - lux_at_min  # Calculates the difference in light between the max and min setting

    global lux_per_bright
    lux_per_bright = lux_diff/100.0  # Calculates how much the light level changes for each step of brightness

    print("Min: " + str(lux_at_min) + " Max: " + str(lux_at_max))
    print("Difference: " + str(lux_diff) + " LuxPerBright: " + str(lux_per_bright))


# Contains the main looping execution of the program
def main():
    print("Running...")
    global current_setting
    while True:
        current_lux = Sensorian_Client.get_light()  # Get the current light level to see if it is in range
        Sensorian_Client.display_values()
        current_difference = current_lux - desired_lux  # Calculate how different the current and desired levels are
        if current_difference < 0 and abs(current_difference) > lux_per_bright:  # If negative difference, check low
            brightness_notches = math.floor(abs(current_difference) / lux_per_bright)  # Calculate how much to change
            current_setting += brightness_notches  # Increase the current brightness by the calculated amount
            print("Light too low, increasing brightness by " + str(brightness_notches) + " to " + str(current_setting))
            if current_setting > 100:  # If the setting attempts to cross the maximum of 100, set it to 100
                print("Can't go brighter than 100, capping it")
                current_setting = 100  # Cap the setting at the maximum of 100
            Sensorian_Client.ifttt_trigger(IFTTT_KEY, IFTTT_EVENT, IFTTT_TIMEOUT, current_setting)
            wait_for_change(current_lux, "UP")  # Waits until the brightness changes/times out
        elif current_difference > 0 and current_difference > lux_per_bright:  # If positive difference, check high
            brightness_notches = math.floor(current_difference / lux_per_bright)  # Calculate how much to change
            current_setting -= brightness_notches  # Decrease the current brightness by the calculated amount
            print("Light too high, decreasing brightness by " + str(brightness_notches) + " to " + str(current_setting))
            if current_setting < 0:  # If the setting attempts to cross the minimum of 0, set it to 0
                print("Can't go darker than 0, capping it")
                current_setting = 0  # Cap the setting at the minimum of 0
            Sensorian_Client.ifttt_trigger(IFTTT_KEY, IFTTT_EVENT, IFTTT_TIMEOUT, current_setting)  # Change brightness
            wait_for_change(current_lux, "DOWN")  # Waits until the brightness changes/times out
        time.sleep(3)  # Wait for 3 seconds between each check for brightness


# Assuming this program is run itself, execute normally
if __name__ == "__main__":
    setup()  # Set up the sensors for use
    calibrate()  # Calibrate the minimum and maximum light levels for the Philips Hue light

    try:  # Try running the main method
        main()
    except KeyboardInterrupt:  # Halt the program when a keyboard interrupt is received from the console
        print("...Quitting ...")
    finally:
        Sensorian_Client.cleanup()
