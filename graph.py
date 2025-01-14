#!/usr/bin/env python

import matplotlib
#from zmq import NULL
matplotlib.use("WxAgg")
from matplotlib.backends.backend_wxagg import (
    FigureCanvasWxAgg as FigureCanvas,
    NavigationToolbar2WxAgg as NavigationToolbar)
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

from numpy import linspace, array, random, where, zeros
from numpy.random import random as rand
import numpy as np

import pdb
import sys
import traceback
import pdb
import time
import pandas as pd

from sys import platform
from threading import RLock
from reader import MonitorThread, ReaderThread

import wx
import serial.tools.list_ports
import subprocess


portInfo = {} #keep track of ports
DELAY_TIME = .01

EVT_COUNTDOWN = wx.NewEventType()
COUNTDOWN_BIND_ID = 101

EVT_COUNTDOWN_EVENT = wx.PyEventBinder(EVT_COUNTDOWN, 1)

class CountdownEvent(wx.PyCommandEvent):
    def __init__(self, eventType, id, count):
        super(CountdownEvent, self).__init__(eventType, id)
        self.count = count

class CountdownPanel(wx.Panel):
    def __init__(self, parent):
        super(CountdownPanel, self).__init__(parent)

        self.countdown_label = wx.StaticText(self, label="", style=wx.ALIGN_CENTER,)
        font = wx.Font(15, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        self.countdown_label.SetFont(font)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.countdown_label, 1, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(sizer)

        self.Hide()

    def update_countdown_label(self, count):
        self.countdown_label.SetLabel(str(count))

    def start_countdown(self, count):
        self.Show()
        self.update_countdown_label(count)

        self.i = count
        while self.i >= 0:
            self.update_countdown_label(self.i)
            self.Raise()
            wx.PostEvent(self.GetParent(), CountdownEvent(EVT_COUNTDOWN, COUNTDOWN_BIND_ID, self.i))
            self.i -= 1
            time.sleep(1)

        self.countdown_label.SetLabel("")
        self.Destroy()
        CanvasFrame.paused = False
        
    def HidePanel(self):
        self.Hide()

def GetGitTag():
    # tag =  subprocess.check_output(['git', 'describe', '--tags'])
    tag = '1.1.3 2024/01/13'
    print(tag)
    return tag

class CustomProgressBar(wx.Panel):
    def __init__(self, parent, id=wx.ID_ANY, size=(250, 25)):
        super().__init__(parent, id, size=size)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.progress = 0
        self.progress_color = wx.Colour(0, 255, 0) 

    def SetValue(self, value):
        self.progress = value
        if self.progress >= 100:
            self.SetColor(wx.Colour(0, 0, 255))  
        self.Refresh()

    def SetColor(self, color):
        self.progress_color = color
        self.Refresh()

    def OnPaint(self, evt):
        width, height = self.GetSize()
        progress_width = int(width * self.progress / 100)
        dc = wx.PaintDC(self)
        dc.SetBrush(wx.Brush(self.progress_color))
        dc.DrawRectangle(0, 0, progress_width, height)



class CanvasFrame(wx.Frame):
    def __init__(self, port = 'COM3:'):
        super(CanvasFrame, self).__init__(None, -1, "Canvas Frame", size=(550, 350))


        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.hbox = wx.BoxSizer(wx.HORIZONTAL)


        self.progressBar = CustomProgressBar(self, size=(250, 25))
        self.hbox.Add(self.progressBar, 0, wx.ALL, 5)

        self.CreateStatusBar()
        self.SetStatusText("Please choose a port")
        self.paused = False
        self.lock = RLock()
        self.lock.acquire()
        self.data = {}
        self.lock.release()
        self.mon = None
        self.timerToggle = False
        self.thresholdToggle = False
        self.time = 0

        self.startTime = 0
        self.displayTime = 0
        self.elapsedTime = 0.0

        self.value = 0
        self.startTime = -1
        self.resetThreshold()
        self.printed = False

        self.mode = 0

        self.timerMode = 2
        self.threshMode = 1
        self.manualMode = 0

        self.figure = Figure()
        self.axes = self.figure.add_subplot()
        self.canvas = FigureCanvas(self, -1, self.figure)
        self.canvas.callbacks.connect('button_release_event', self.on_button_release)

        self.sizer.Add(self.hbox, 0, wx.LEFT | wx.BOTTOM)
        self.SetSizer(self.sizer)
        self.Fit()

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.canvas, 1, wx.LEFT | wx.TOP | wx.EXPAND)
        self.SetSizer(self.sizer)
        self.Fit()

        self.hbox = wx.BoxSizer(wx.HORIZONTAL)

        #lblList = ['Manual', 'Threshold', 'Timer'] 
        #self.rbox = wx.RadioBox(self, label = 'Mode', pos = (0,0), choices = lblList, majorDimension = 3, style = wx.RA_SPECIFY_ROWS) 

        #self.l1 = wx.StaticText(self, -1, " Input")
        #self.t1 = wx.TextCtrl(self) 
        
        self.clearButton = wx.Button(self, label="Restart")
        self.saveButton = wx.Button(self, label="Save Data")
        self.pauseButton = wx.Button(self, label="Start")

        #self.hbox.Add(self.rbox, 10)
        #self.hbox.Add(self.l1, 10)
        #self.hbox.Add(self.t1, 30)

        self.hbox.Add(self.clearButton, 20)
        self.hbox.Add(self.saveButton, 20)
        self.hbox.Add(self.pauseButton, 20)

        self.pauseButton.Disable()
        self.saveButton.Disable()
        self.clearButton.Disable()

        self.axes.grid()
        self.axes.set_ylim([250,600])
        self.sizer.Add(self.hbox, 0, wx.LEFT | wx.BOTTOM)

        self.clearButton.Bind(wx.EVT_BUTTON, self.OnClear)
        self.saveButton.Bind(wx.EVT_BUTTON, self.OnSave)
        self.pauseButton.Bind(wx.EVT_BUTTON, self.OnPause)

        self.add_toolbar()  # comment this out for no toolbar
        self.add_menu()

        TIMER_ID = 1

        self.timer = wx.Timer(self, TIMER_ID)
        self.Bind(wx.EVT_TIMER, self.ontimer, self.timer)
        self.timer.Start(15)

        self.mon = MonitorThread(callback=self.dataCallback)
        # self.mon.reader.paused = False
        self.lock.acquire()
        self.data = {}
        self.lock.release()
        self.mon.start()
        self.paused = True
        #self.OnPause()

        #fix this
    def update_status(self, message):
        self.SetStatusText(message)

    def open_port(self, portname):
        self.update_status("collecting data")
        self.mon.openport(portname)
   
    def on_button_release(self, event):
        t = np.array(self.data.get('times',[]))
        v = np.array(self.data.get('values',[]))
        xlim = self.axes.get_xlim()
        ylim = self.axes.get_ylim()
        inside = (t < xlim[1]) & (t > xlim[0])
        self.update_status(f"max: {min(np.max(v[inside]),ylim[1]):0.3f}")

    def add_menu(self):
        menubar = wx.MenuBar() 
      
        fileMenu = wx.Menu() 
        ports = serial.tools.list_ports.comports()
        for ix in range(len(ports)):
            port=ports[ix]
            print(port)
            menuID=ix+100
            print(menuID)
            portInfo[menuID] = port.device
           
            fileMenu.AppendItem(wx.MenuItem(fileMenu, menuID,text = port.name)) 
        fileMenu.AppendSeparator() 
        
     
        quit = wx.MenuItem(fileMenu, wx.ID_EXIT, '&Quit') 
      
        fileMenu.AppendItem(quit) 
        menubar.Append(fileMenu, '&Change Port') 

        version = GetGitTag()
        info = "UIndy Team Data (ENGR 298) - Plotter"
        names = "Rainey Biggerstaff, Bryson Walker, Param Dhaliwal, Rakan Abu Shanab, Avery Eller, Steve Spicklemire"
        aboutMenu = wx.Menu()
        menubar.Append(aboutMenu, 'About')

        versionTxt = wx.MenuItem(aboutMenu, wx.ID_ANY, version)
        infoTxt = wx.MenuItem(aboutMenu, wx.ID_ANY, info)
        namesTxt = wx.MenuItem(aboutMenu, wx.ID_ANY, names)
    
        aboutMenu.Append(versionTxt)
        aboutMenu.Append(infoTxt)
        aboutMenu.Append(namesTxt)

        image = wx.Bitmap("image.png", wx.BITMAP_TYPE_PNG)

        # aboutMenu.Append(wx.ID_ANY, "Image Button", bitmap=image)

        bmp_item = wx.MenuItem(aboutMenu, wx.ID_ANY, " ")
        bmp_item.SetBitmap(image)  
        aboutMenu.Append(bmp_item)  

        self.SetMenuBar(menubar) 
        self.text = wx.TextCtrl(self,-1, style = wx.EXPAND|wx.TE_MULTILINE) 
        self.Bind(wx.EVT_MENU, self.menuhandler) 
        self.SetSize((800, 700)) 
        self.Centre() 
        self.Show(True)

        #app = wx.App()
        #wx.MessageBox('Pythonspot wxWidgets demo', 'Info', wx.OK | wx.ICON_INFORMATION)
      
        self.SetMenuBar(menubar) 
        self.text = wx.TextCtrl(self,-1, style = wx.EXPAND|wx.TE_MULTILINE) 
        self.Bind(wx.EVT_MENU, self.menuhandler) 
        self.SetSize((800, 700)) 
        self.Centre() 
        self.Show(True)

  
    def menuhandler(self, event):
        id = event.GetId() 
        print(id)
        if id in portInfo:
            self.pauseButton.Enable()
            self.saveButton.Enable()
            self.clearButton.Enable()

            if platform == "darwin":
                self.open_port(portInfo[id])
            elif platform == "win32":
                self.open_port(portInfo[id]+":")
            self.lock.acquire()
            self.data = {}
            self.lock.release()
        if id == wx.ID_EXIT:
            print("closing....")
            if self.mon:
                self.mon.closeports()
                del self.mon
                self.mon = None
            self.Close()

    def add_toolbar(self):
        self.toolbar = NavigationToolbar(self.canvas)
        self.toolbar.Realize()
        # By adding toolbar in sizer, we are able to put it at the bottom
        # of the frame - so appearance is closer to GTK version.
        self.sizer.Add(self.toolbar, 0, wx.LEFT | wx.EXPAND)
        # update the axes menu on the toolbar
        self.toolbar.update()
           
    def OnClear(self, evt):
        self.mon.reader.paused = True
        time.sleep(DELAY_TIME)
        self.lock.acquire()
        self.data = {}
        self.resetThreshold()
        self.mon.reader.resetStartTime()
        self.mon.sender.emptyQ()
        self.mon.reader.emptyQ()
        self.lock.release()
        self.startTime = int(time.time())
        self.displayTime = 0
        self.mon.reader.paused = False
        if self.mon:
            self.mon.resetTime()
        if self.mode == self.timerMode:
            self.startTime = int(time.time())

        self.pauseButton.SetLabel("Stop")
        self.paused = False
        
    def OnPause(self, evt):
        id = evt.GetId()
        if (self.startTime == 0):
            self.startTime = time.time()
        if not self.paused:
            self.paused = not self.paused
            self.pauseButton.SetLabel("Start")
            self.update_status("paused")
        else:
            self.pauseButton.SetLabel("Stop")
            #self.countdown = CountdownPanel(self)
            #self.sizer.Add(self.countdown,1,wx.EXPAND)
            self.lock.acquire()
            self.mon.sender.emptyQ()
            self.mon.reader.emptyQ()
            self.lock.release()
            #self.countdown.start_countdown(3)
                
            
            self.paused = not self.paused
            self.printed = False
            if((self.mode == self.timerMode) and int(time.time() - self.startTime) >= self.value):
                self.OnClear(evt)
            if(self.mode == self.threshMode):
                self.OnClear(evt)   
            self.pauseButton.SetLabel("Stop") 
            self.update_status("collecting data...")
            
    def OnTogglePlotType(self, evt):
        if self.plotType == ICVSIB:
            self.plotType = ICVSVC
            self.plotTypeButton.SetLabel(ICVSIB_Label)
        else:
            self.plotType = ICVSIB
            self.plotTypeButton.SetLabel(ICVSVC_Label)
        
    def OnSave(self, evt):
        self.lock.acquire()
        fdlg = wx.FileDialog(self, "Save File", "", "", "Excel files (*.xlsx)|*.xlsx",  wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if fdlg.ShowModal() == wx.ID_OK:
            self.save_path = fdlg.GetPath()
            df = pd.DataFrame(self.data)
            df.to_excel(self.save_path, index=False)
        self.update_status("Saving data...")
        self.lock.release()
        
    def ontimer(self, evt):
        if self.mon:
            self.update_plot()
            self.canvas.draw()
        
    def resetThreshold(self):
        self.thresholdSum = -1
        self.vLast = 0
        self.tLast = 0

    def thresholdCalculation(self, items):
        if not self.paused:     
            if self.mode == self.threshMode:
                #print(self.thresholdSum)
                for val,t in items:
                    dt = t-self.tLast - self.startTime
                    vavg = ((val-250)+self.vLast)/2
                    self.thresholdSum += vavg * dt
                    self.vLast = val-250
                    self.tLast = t - self.startTime
                if (self.thresholdSum >= self.value):
                    pass
                    #print(self.thresholdSum)
                    #print(self.value)
                    #print("reset threshold")
                    # self.resetThreshold()
                    # self.paused = True

    def onRadioBox(self, evt):
        if(self.paused == False):
            self.OnPause(evt)
        if(self.rbox.GetStringSelection() == "Timer"):
            self.pauseButton.Hide()
            #Timer UI
            self.t1.Enable()
            self.value = 0
            self.t1.SetValue('')
            self.mode = self.timerMode
            self.OnClear(evt)
            if(self.paused == False):
                self.OnPause(evt)
            #print("radioTime")

        if(self.rbox.GetStringSelection() == "Threshold"):
            #Timer UI
            self.pauseButton.Hide()
            self.t1.Enable()
            self.value = 0
            self.t1.SetValue('')
            self.mode = self.threshMode
            self.OnClear(evt)
            if(self.paused == False):
                self.OnPause(evt)
            #print("radioThresh")
 
        if(self.rbox.GetStringSelection() == "Manual"):
            #Manual UI
            
            self.pauseButton.Show()
            self.t1.Disable()
            self.value = 0
            self.t1.SetValue('')
            self.mode = self.manualMode
            self.OnClear(evt)
            if(self.paused == False):
                self.OnPause(evt)

    def dataCallback(self, items):
        self.lock.acquire()
        for val,t in items:
            if self.paused:
                self.startTime = t - self.displayTime
                #print("in dataCallBack Paused")
            else:
                self.displayTime = t - self.startTime
                self.data['values'] = self.data.get('values',[])+[val]
                self.data['times'] = self.data.get('times',[])+[self.displayTime] 
                if not self.printed:
                    #print(t)  
                    self.printed = True   
        self.lock.release()
        self.thresholdCalculation(items)

    def plot_data(self):
        if not self.paused and self.data.get('values',[]):    
            self.lock.acquire()
            self.axes.clear()
            self.axes.plot(self.data['times'], self.data['values'],label="Force")
            #self.axes.set_ylim([250,600])
            self.axes.grid()
            #self.axes.set_title(r"Pressure Graph")
            self.axes.set_xlabel("time (s)")
            self.axes.set_ylabel("Force (Lb)")
            self.lock.release()
            #self.t1.Disable()
            self.stop_plot()

            if self.mon and (self.mode == self.timerMode) and self.value > 0:
                self.progressBar.Show()
                elapsed_time = time.time() - self.startTime 
                progress = (elapsed_time / self.value) * 100
                self.progressBar.SetValue(min(int(progress), 100))
                self.progressBar.SetColor(wx.Colour(0, 255, 0))
        
            
            if self.mon and (self.mode == self.threshMode) and self.value > 0:
                self.progressBar.Show()
                elapsed_thresh = self.thresholdSum - 1 
                progress = (elapsed_thresh / self.value) * 100
                #print(progress)
                self.progressBar.SetValue(min(int(progress), 100))
                self.progressBar.SetColor(wx.Colour(0, 255, 0))


            if self.mode == self.manualMode:
                self.progressBar.Hide()
                
            if self.progressBar.progress >= 100:
                self.paused = True

        
        #if self.paused:  
        #    self.t1.Enable()
            
        #if self.paused:
        #    if self.progressBar.progress >= 100:
        #        self.progressBar.Show()
        #        self.progressBar.SetColor(wx.Colour(0, 0, 255))

        # if self.progressBar.progress >= 100:
        #     self.progressBar.SetColor(wx.Colour(0, 0, 255))
    
    def stop_plot(self):
        #print(int(time.time()))
        if((self.mode == self.timerMode) and int(time.time() - self.startTime) >= self.value):
            self.paused = True

    def update_plot(self):
        self.plot_data()

    def OnPaint(self, event):
        self.update_plot()
        self.canvas.draw()

    def Ask(self, parent=None, message='', default_value=''):
        result = -1
        if(1):
            dlg = wx.TextEntryDialog(parent, message, default_value)
            dlg.ShowModal()
            result = dlg.GetValue()
            dlg.Destroy()
        return int(result)     
    
    def OnKeyTyped(self, event):
        try:
            self.value = int(event.GetString())
        except ValueError:
            print("Invalid input")

class MyApp(wx.App):
    def setPort(self, port='COM3:'):
        print("SetPort")
        self.port = port
    def OnInit(self):
        print("OnInit")
        frame = CanvasFrame(port=port)
        frame.Show(True)
        return True

import os
print ("Here now:", os.getcwd())
if(len(sys.argv)>1):
    port = sys.argv[1]
else:
    port = 'COM3:'
app = MyApp()
#app.setPort(port)
#pdb.set_trace()
app.MainLoop()