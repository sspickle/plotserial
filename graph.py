#!/usr/bin/env python

import matplotlib
matplotlib.use("WxAgg")
from matplotlib.backends.backend_wxagg import (
    FigureCanvasWxAgg as FigureCanvas,
    NavigationToolbar2WxAgg as NavigationToolbar)
from matplotlib.figure import Figure

from numpy import linspace, array, random, where, zeros
from numpy.random import random as rand
import numpy as np

import sys
import traceback
import pdb

from threading import RLock
from reader import MonitorThread

import wx

vRawMax = 4096
vMax = 6*1.024
rBase =22e3
rColl = 220

ICVSIB = 0
ICVSVC = 1
ICVSIB_Label = "Ic vs Ib"
ICVSVC_Label = "Ic vs Vc"

def getVals(k, frame):
    d = np.array(frame.data[k])
    bd,cd,bp,bm,cm,cp = d[:,0],d[:,1],d[:,2],d[:,3],d[:,4],d[:,5]
    return {'bd': bd, 'cd': cd, 'bp': bp, 'bm': bm, 'cp': cp, 'cm': cm}

def calcCurrents(k, frame):
    vals = getVals(k, frame)
    dvBase = vMax*(vals['bp'] - vals['bm'])/vRawMax
    iBase = dvBase/rBase
    vcd = vMax*vals['cp']/vRawMax
    vc = vMax*vals['cm']/vRawMax
    dvColl = vcd - vc
    iColl = dvColl/rColl
    return {'iBase': iBase, 'iColl': iColl, 'vc':vc}

class CanvasFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, -1, 'CanvasFrame', size=(550, 350))
        
        self.paused = False
        self.plotType = ICVSVC
        self.lock = RLock()
        self.data = {}

        self.figure = Figure()
        self.axes = self.figure.add_subplot()

        self.canvas = FigureCanvas(self, -1, self.figure)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.canvas, 1, wx.LEFT | wx.TOP | wx.EXPAND)
        self.SetSizer(self.sizer)
        self.Fit()
        
        self.hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        self.clearButton = wx.Button(self, label="Clear")
        self.saveButton = wx.Button(self, label="Save Data")
        self.pauseButton = wx.Button(self, label="Pause")
        self.plotTypeButton = wx.Button(self, label=ICVSIB_Label)
        self.hbox.Add(self.clearButton, 0)
        self.hbox.Add(self.saveButton, 20)
        self.hbox.Add(self.pauseButton, 20)
        self.hbox.Add(self.plotTypeButton, 20)

        self.sizer.Add(self.hbox, 0, wx.LEFT | wx.BOTTOM)

        self.clearButton.Bind(wx.EVT_BUTTON, self.OnClear)
        self.saveButton.Bind(wx.EVT_BUTTON, self.OnSave)
        self.pauseButton.Bind(wx.EVT_BUTTON, self.OnPause)
        self.plotTypeButton.Bind(wx.EVT_BUTTON, self.OnTogglePlotType)

        self.add_toolbar()  # comment this out for no toolbar
        self.update_plot()

        TIMER_ID = 1

        self.timer = wx.Timer(self, TIMER_ID)
        self.Bind(wx.EVT_TIMER, self.ontimer, self.timer)
        self.timer.Start(1000)
        
        self.mon = MonitorThread(callback=self.dataCallback)
        self.mon.start()

    def add_toolbar(self):
        self.toolbar = NavigationToolbar(self.canvas)
        self.toolbar.Realize()
        # By adding toolbar in sizer, we are able to put it at the bottom
        # of the frame - so appearance is closer to GTK version.
        self.sizer.Add(self.toolbar, 0, wx.LEFT | wx.EXPAND)
        # update the axes menu on the toolbar
        self.toolbar.update()
           
    def OnClear(self, evt):
        self.data = {}
        
    def OnPause(self, evt):
        self.paused = not self.paused
        if self.paused:
            self.pauseButton.SetLabel("Resume")
        else:
            self.pauseButton.SetLabel("Pause")
            
    def OnTogglePlotType(self, evt):
        if self.plotType == ICVSIB:
            self.plotType = ICVSVC
            self.plotTypeButton.SetLabel(ICVSIB_Label)
        else:
            self.plotType = ICVSIB
            self.plotTypeButton.SetLabel(ICVSVC_Label)
        
    def OnSave(self, evt):
        self.lock.acquire()

        fdlg = wx.FileDialog(self, "Save File", "", "", "PY files(*.py)|*.*",  wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)

        if fdlg.ShowModal() == wx.ID_OK:
            self.save_path = fdlg.GetPath() + ".py"

            with open(self.save_path, "w") as file:
                file.write("data = " + str(self.data))

        self.lock.release()
        
    def ontimer(self, evt):
        self.update_plot()
        self.canvas.draw()
        
        
    def dataCallback(self, items):
        self.lock.acquire()
        key = items[0][0][0]
        self.data[key] = items[0]
        self.lock.release()

    def plot_icvsvc(self):
        if not self.paused:
            self.lock.acquire()
            self.axes.clear()
            #self.axes.plot(range(100),range(100), 'b-')
            for k in sorted(list(self.data.keys())):
                currObjs = calcCurrents(k,self)
                ibMean = currObjs['iBase'].mean()
                self.axes.plot(currObjs['vc'], 1000*currObjs['iColl'],label="$I_{b}$ = %.1f $\mu$A" % (ibMean*1e6))
            self.axes.grid()
            self.axes.legend()
            self.axes.set_xlabel('Vc (V)')
            self.axes.set_ylabel('Ic (mA)')
            self.lock.release()

    def plot_icvsib(self):
        if not self.paused:
            self.lock.acquire()
            self.axes.clear()
            #self.axes.plot(range(100),range(100), 'b-')
            for k in sorted(list(self.data.keys())):
                currObjs = calcCurrents(k,self)
                ibMean = currObjs['iBase'].mean()
                self.axes.plot(currObjs['iBase']*1e6, 1000*currObjs['iColl'],label="$I_{b}$ = %.1f $\mu$A" % (ibMean*1e6))
            self.axes.grid()
            self.axes.legend()
            self.axes.set_xlabel('Ib (uA)')
            self.axes.set_ylabel('Ic (mA)')
            self.lock.release()

    def update_plot(self):
        if self.plotType == ICVSVC:
            self.plot_icvsvc()
        else:
            self.plot_icvsib()

    def OnPaint(self, event):
        self.update_plot()
        self.canvas.draw()
        

class MyApp(wx.App):
    def OnInit(self):
        frame = CanvasFrame()
        frame.Show(True)
        return True

import os
print ("Here now:", os.getcwd())
app = MyApp()
#pdb.set_trace()
app.MainLoop()