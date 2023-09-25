#!/usr/bin/env python
#

import os
import select
import sys
import time
import string
import traceback
import getopt
import traceback
import serial


def log(msg):
    sys.stdout.write('LOG ' + time.ctime(time.time()) + ":" + msg + '\n')
    sys.stdout.flush()

from threading import *

class ThreadQueue:

    def __init__(self):
        self.mon = RLock()
        self.queue = []

    def put(self, item):
        self.mon.acquire()
        self.queue.append(item)
        self.mon.release()

    def get(self):
        item = None
        if len(self.queue):
            self.mon.acquire()
            item = self.queue[0]
            del self.queue[0]
            self.mon.release()
            
        return item
        
        
class ReaderThread (Thread):

    def __init__(self):
        Thread.__init__(self, name="Reader")
        self.setDaemon(1)
        self.recvQueue = ThreadQueue()
        self.foundLabels = False
        self.gotStart = False

    def run(self):
        self.port = serial.Serial('/dev/cu.usbserial-8340', baudrate=9600)

        while 1:
            while 1:
                s = ''
                try:
                    inval = self.port.readline()
                    s = inval.decode().strip()           # read a line of input from the Arduino
                except UnicodeDecodeError:
                    print("Ack decode error:", inval)

                try:
                    val = eval(s)
                    self.recvQueue.put(val)
                except (ValueError, SyntaxError, NameError) as e:
                    print ("Ack. conversion error:" + str(s), "keep trying...")

    def get(self):
        return self.recvQueue.get()
        
    def send(self, msg):
        """
        Send typed message to port
        """
        self.port.write(msg.encode())
        
class SenderThread(Thread):
    
    def __init__(self, callback=None):
        Thread.__init__(self, name="Sender")
        self.setDaemon(1)
        self.queue = ThreadQueue()
        self.callback = callback

    def put(self, item):
        self.queue.put(item)
        
    def run(self):
        while 1:
            time.sleep(0.1)
            items = []

            while 1:
                item = self.queue.get()
                if not item:
                    break
                
                items.append(item)
                
            if items:
                if self.callback:
                    self.callback( items )

class MonitorThread(Thread):

    def __init__(self, callback=None, fr=None):
        Thread.__init__(self, name="Monitor")
        self.setDaemon(1)
        self.callback = callback
        self.reader = None
        self.sender = None
        self.fr = fr
        log("Monitor thread inited with callback=" + str(callback))
        
    def run(self):
        
        self.reader = ReaderThread()
        self.sender = SenderThread(callback=self.callback)
        
        #
        # start the threads.
        #
        
        self.reader.start()
        self.sender.start()
        
        while 1:
            time.sleep(0.1)
            while 1:
                qItem = self.reader.get()
                if qItem:
                    self.sender.put(qItem)
                else:
                    break
                
    def __del__(self):
        print("In monitor delete...")
       
        if self.reader:
            self.reader.kill_pipe()
            del self.reader
            
        if self.sender:
            del self.sender
        

def monitorPort(test=0):
    
    monitor = MonitorThread(callback = testCallback, fr=0)
    monitor.start()
    
    while 1:
        time.sleep(0.1) # sit around and wait for things to happen.
        
def testCallback( item ):
    print ("in callback")
    sys.stdout.flush()
    log("Callback for " + str(item))

def usage():
    print ("Usage: %s [-d|--debug] [-p|--pdb] [-u|--url url] [-s|--sleepInt floatValue]" % sys.argv[0])
    print ("""

    -p, --pdb               : break after parsing options
    -u, --url  url          : url to send xmlrpc notifications
    -P, --port  portName    : name of serial port (e.g., '/dev/cuaa0')
    """)
    sys.exit(2)
        
def main():
    """
    For command line use.
    """
    try:
        opts, args = getopt.getopt(sys.argv[1:], "pu:", ["pdb"])
            
    except getopt.error:
        # print help information and exit:
        usage()

    debug = 0
    doPDB = 0
    sleepInterval=2.0

    for o, a in opts:

        if o in ("-p", "--pdb"):
            doPDB=1

    if doPDB:
        import pdb
        pdb.set_trace()

    monitorPort()
        
if __name__=="__main__":
    main()
