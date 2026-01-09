#!/usr/bin/python3
#Imports

import time
import os
#When running as service, need to flush stdout so it's logged
#https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html
import sys

#https://www.instructables.com/Raspberry-Pi-Tutorial-How-to-Use-the-DHT-22/
#git clone https://github.com/adafruit/Adafruit_Python_DHT.git
import Adafruit_DHT as dht

#https://randomnerdtutorials.com/raspberry-pi-digital-inputs-python/
#https://miketrebilcock.github.io/js-gpiozero/DigitalOutputDevice.html  ?
from gpiozero import DigitalOutputDevice

#https://www.waveshare.com/wiki/1.3inch_OLED_HAT
import SH1106
import config
import traceback
from PIL import Image,ImageDraw,ImageFont

#Threading
import multiprocessing


#Display setup and variables
try:
    display = SH1106.SH1106()
    display.Init()
    display.clear()
except IOError as e:
    print(e)
font = ImageFont.truetype('Font.ttf',11)

#Setup and Globals

#Humidity and Temperature
humidTarget = 50
humidDelta = 5
fanOn = False
tempTarget = 50
tempDelta = 2
heatOn = False

#GPIO
fanPin = 14
heaterPin = 15
humidPin = 23
humidPowerPin = 18
fanOutput = DigitalOutputDevice(fanPin)
heaterOutput = DigitalOutputDevice(heaterPin)

#Other globals
sensorLastRead = 0
humidTemp = (0, 0)
buttonTime = 0
heatFanMaxTime = 300 #5 minutes
heatFanOnTime = 0

#Temp Target          Temp Delta
#Humid Target         Humid Delta
menuCol = 0
menuRow = 0

#Functions

def HumidTempOff(humidTempPwrOutput):
    humidTempPwrOutput.off()

def HumidTempOn(humidTempPwrOutput):
    humidTempPwrOutput.on()

def HumidTempCycle(humidTempPwrOutput):
    HumidTempOff(humidTempPwrOutput)
    time.sleep(3)
    HumidTempOn(humidTempPwrOutput)

def ReadHumidTemp(humid_pin, humid_pwr_pin, humid_temp_pipe, log_pipe):
    humidTempPwrOutput = DigitalOutputDevice(humid_pwr_pin)
    log_pipe.send('DHT22 power on')
    HumidTempOn(humidTempPwrOutput)
    lastRead = time.time()
                
    hp = humid_pin
    log_pipe.send('Main Process: %d' % os.getppid())
    log_pipe.send('HT Process: %d' % os.getpid())
    try:
        while True:
            time.sleep(5)
            #Check time first
            if time.time() - lastRead > 300:
                lastRead = time.time()
                log_pipe.send('Cycling DHT22 power %s' % time.asctime(time.gmtime()))
                HumidTempCycle(humidTempPwrOutput)
                log_pipe.send('DHT22 power on %s' % time.asctime(time.gmtime()))
            h,t = dht.read_retry(dht.DHT22, hp)
            if t is None:
                continue
            t = (t * 9 / 5) + 32
            lastRead = time.time()
            log_pipe.send('{0:0.1f}*F  {1:0.1f}%  {2:s}'.format(t,h,time.asctime(time.gmtime())))
            humid_temp_pipe.send((h,t))
    except KeyboardInterrupt:
        print("HT_KeyboardInterrupt")
        
def UpdateDisplay():
    global menuRow
    global menuCol
    global humidTarget
    global tempTarget
    global humidDelta
    global tempDelta
    global humidTemp
    #Create all the strings first
    if humidTemp is None:
        humidTempStatus = "Humidity:%d%%  Temp:%dF" % (0,0)
    else:
        humidTempStatus = "Humidity:%d%%  Temp:%dF" % humidTemp
    fanStatus = "ON" if fanOn else "OFF"
    fanStatus = "Fan:" + fanStatus
    heatStatus = "ON" if heatOn else "OFF"
    heatStatus = "Heater:" + heatStatus
    heatFanStatus = heatStatus + "  " + fanStatus
    #Target strings
    tempTargetStatus = "Target[F]:%d" % tempTarget
    tempDeltaStatus = "Δ[F]:%d" % tempDelta
    humidTargetStatus = "Target[%%]:%d" % humidTarget
    humidDeltaStatus = "Δ[%%]:%d" % humidDelta
    #Prepend a '-' to whatever is selected
    if menuCol == 0:
        if menuRow == 0:
            tempTargetStatus = "-" + tempTargetStatus
            tempDeltaStatus = " " + tempDeltaStatus
            humidTargetStatus = " " + humidTargetStatus
            humidDeltaStatus = " " + humidDeltaStatus
        else:
            tempTargetStatus = " " + tempTargetStatus
            tempDeltaStatus = " " + tempDeltaStatus
            humidTargetStatus = "-" + humidTargetStatus
            humidDeltaStatus = " " + humidDeltaStatus
    else:
        if menuRow == 0:
            tempTargetStatus = " " + tempTargetStatus
            tempDeltaStatus = "-" + tempDeltaStatus
            humidTargetStatus = " " + humidTargetStatus
            humidDeltaStatus = " " + humidDeltaStatus
        else:
            tempTargetStatus = " " + tempTargetStatus
            tempDeltaStatus = " " + tempDeltaStatus
            humidTargetStatus = " " + humidTargetStatus
            humidDeltaStatus = "-" + humidDeltaStatus
    
    #Create image that we'll use
    imageDisplay = Image.new('1', (display.width, display.height), "WHITE")
    draw = ImageDraw.Draw(imageDisplay)
    
    
    #Draw the strings to the image
    draw.text((0,0), humidTempStatus, font=font, fill=0)
    draw.text((0,15), heatFanStatus, font=font, fill=0)
    draw.text((0,30), tempTargetStatus + "  " + tempDeltaStatus, font=font, fill=0)
    draw.text((0,45), humidTargetStatus + "  " + humidDeltaStatus, font=font, fill=0)
    
    #Draw the image to the display
    display.ShowImage(display.getbuffer(imageDisplay))
    
def ReadButtons():
    global menuRow
    global menuCol
    global humidTarget
    global tempTarget
    global humidDelta
    global tempDelta
    global buttonTime
    buttonUp =       True if display.RPI.digital_read(display.RPI.GPIO_KEY_UP_PIN )    != 0 else False
    buttonDown =     True if display.RPI.digital_read(display.RPI.GPIO_KEY_DOWN_PIN )  != 0 else False
    buttonLeft =     True if display.RPI.digital_read(display.RPI.GPIO_KEY_LEFT_PIN )  != 0 else False
    buttonRight =    True if display.RPI.digital_read(display.RPI.GPIO_KEY_RIGHT_PIN ) != 0 else False
    buttonIncrease = True if display.RPI.digital_read(display.RPI.GPIO_KEY1_PIN )      != 0 else False
    buttonDecrease = True if display.RPI.digital_read(display.RPI.GPIO_KEY3_PIN )      != 0 else False
    
    #See if there are any pressed buttons
    if buttonUp is False and buttonDown is False and buttonLeft is False and buttonRight is False and buttonIncrease is False and buttonDecrease is False:
        return False
    #Only register button if at least .2 seconds have passed
    now = time.time()
    if now - buttonTime < .2:
        return False
    buttonTime = time.time()
    
    #Figure out which button is pressed: Either move menu selection or increase/decrease value
    changeValue = 0
    if buttonUp is True:
        if menuRow == 1:
            menuRow = 0
        return True
    elif buttonDown is True:
        if menuRow == 0:
            menuRow = 1
        return True
    elif buttonLeft is True:
        if menuCol == 1:
            menuCol = 0
        return True
    elif buttonRight is True:
        if menuCol == 0:
            menuCol = 1
        return True
    elif buttonIncrease is True:
        changeValue = 1
    elif buttonDecrease is True:
        changeValue = -1

    #If we get this far, all that's left is possible increase/decrease
    if changeValue == 0:
        #No buttons are pressed
        return False
    if menuCol == 0:
        if menuRow == 0:
            tempTarget += changeValue
            print('TempTarget:%d' % tempTarget)
        else:
            humidTarget += changeValue
            print('HumidTarget:%d' % humidTarget)
    else:
        if menuRow == 0:
            tempDelta += changeValue
            if tempDelta < 1:
                tempDelta = 1
            print('TempDelta:%d' % tempDelta)
        else:
            humidDelta += changeValue
            if humidDelta < 1:
                humidDelta = 1
            print('HumidDelta:%d' % humidDelta)
    return True
    
#Main Loop
if __name__ =="__main__":
    humidTempParent,humidTempChild = multiprocessing.Pipe()
    logParent,logChild = multiprocessing.Pipe()
    processDHT = multiprocessing.Process(target=ReadHumidTemp, name='thrDHT', args=(humidPin,humidPowerPin,humidTempChild,logChild))
    processDHT.start()
    updateDisplayNow = True
    heatFanOnTime = time.time()
    while True:
        try:
            time.sleep(0.05)

            #dht takes a few to read, so wait 10 sec before checking
            now = time.time()
            if now - sensorLastRead > 5:
                #Print everything the parent process has sent
                while logParent.poll() is True:
                    print(logParent.recv())
                sys.stdout.flush()      
                #Read the sensor
                sensorLastRead = time.time()
                if humidTempParent.poll() is False:
                    continue
                #There is a new reading, get the most recent
                while humidTempParent.poll() is True:
                    humidTemp = humidTempParent.recv()          
                updateDisplayNow = True
                #Reset the failsafe time
                heatFanOnTime = now

                #Turn Fan on/off
                humidHigh = humidTarget + humidDelta
                humidLow = humidTarget - humidDelta
                if humidTemp[0] > humidHigh:
                    if fanOn is False:
                        #turn intake fan on
                        print('fan on')
                        fanOutput.on()
                        fanOn = True
                        heatFanOnTime = time.time()
                elif humidTemp[0] < humidTarget:
                    if fanOn is True:
                        #turn intake fan off
                        print('fan off')
                        fanOutput.off()
                        fanOn = False
                #Turn Heater on/off
                tempHigh = tempTarget + tempDelta
                tempLow = tempTarget - tempDelta
                if humidTemp[1] > tempTarget:
                    if heatOn is True:
                        #turn heat off
                        print('heat off')
                        heaterOutput.off()
                        heatOn = False
                elif humidTemp[1] < tempLow:
                    if heatOn is False:
                        #turn heat on
                        print('heat on')
                        heaterOutput.on()
                        heatOn = True
                        heatFanOnTime = time.time()
                sys.stdout.flush()

            #Failsafe to turn off heat/fan
            now = time.time()
            if now - heatFanOnTime > heatFanMaxTime:
                if fanOn:
                    fanOn = False
                    fanOutput.off()
                    print('fan off failsafe')
                elif heatOn:
                    heatOn = False
                    heaterOutput.off()
                    print('heat off failsafe')

            #Read Buttons, handle menu stuff
            if ReadButtons() is True or updateDisplayNow is True:
                #Now update the display
                UpdateDisplay()
                updateDisplayNow = False
        except KeyboardInterrupt:
            print("Keyboard Interrupt")
            break
    processDHT.join()
