"""
single_stream_rtsp_1.py : A demo program: streaming from a single rtsp camera.  Using x window create by Valkka.

Copyright 2017, 2018 Sampsa Riikonen

Authors: Sampsa Riikonen

This file is part of the Valkka Python3 examples library

Valkka Python3 examples library is free software: you can redistribute it and/or modify it under the terms of the MIT License.  This code is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the MIT License for more details.

@file    single_stream_rtsp_1.py
@author  Sampsa Riikonen
@date    2018
@version 1.2.2 
@brief   A demo program: streaming from a single rtsp camera.  You can use an x window create by Valkka.
"""

# from PyQt5 import QtWidgets, QtCore, QtGui # If you use PyQt5, be aware of the licensing consequences
from PySide2 import QtWidgets, QtCore, QtGui
import sys
from valkka.core import *  # API level 1 import

# valkka_xwin =True # use x windows create by Valkka and embed them into Qt
valkka_xwin = False  # use Qt provided x windows


class TestWidget0(QtWidgets.QWidget):

    def mouseDoubleClickEvent(self, e):
        print("double click!")


class WidgetPair:
    """Creates a "foreign" QWidget by using the X window id win_id.  Another "top" widget is placed on top of the foreign widget that catches the mouse gestures.  

    :param parent:       Parent (a QWidget) of the widget pair
    :param win_id:       An X-window id of the foreign window (that's used for streaming)
    :param widget_class: Class of the top widget
    """

    def __init__(self, parent, win_id, widget_class):
        self.win_id = win_id
        self.foreign_window = QtGui.QWindow.fromWinId(win_id)
        self.foreign_widget = QtWidgets.QWidget.createWindowContainer(
            self.foreign_window, parent=parent)

        self.widget = widget_class(self.foreign_widget)
        self.lay = QtWidgets.QHBoxLayout(self.foreign_widget)
        self.lay.addWidget(self.widget)

    def getStreamWindowId():
        """Returns the X-window id for streaming
        """
        return self.win_id

    def getTopWidget():
        """Returns the widget that catches mouse gestures
        """
        return self.widget

    def getWidget(self):
        """Returns the foreign widget (where the stream is going).  This widget is used in layouts.
        """
        return self.foreign_widget


class MyGui(QtWidgets.QMainWindow):
    """A simple Qt main window.  

    Creating the filterchain and starting valkka threads is done in method openValkka.  Stopping valkka threads done in closeValkka.
    """

    def __init__(self, parent=None, stream_address=None):
        super(MyGui, self).__init__()
        self.setupUi()
        if (stream_address == None):
            print("Stream not specified!")
            return
        else:
            self.stream_address = stream_address
        self.openValkka()
        self.start_streams()

    def setupUi(self):
        self.setGeometry(QtCore.QRect(100, 100, 500, 500))
        self.w = QtWidgets.QWidget(self)
        self.setCentralWidget(self.w)
        self.lay = QtWidgets.QVBoxLayout(self.w)

    def openValkka(self):
        """
        filtergraph:

        (LiveThread:livethread) --> {InfoFrameFilter:live_out_filter} -->> (AVThread:avthread) -->> (OpenGLThread:glthread)

        First instantiate OpenGLThread.  This thread does all openGL calls.  It also times and presents all frames.  Memory is pre-reserved on the GPU, so we have to specify how many frames are reserved for each resolution.  You can use the following formula:

        Number of frames for resolution n = buffering time * (frames per second of one camera) * number of cameras for resolution n

        Number of frames (and other parameters) are defined with OpenGLFrameFifoContext
        """
        self.gl_ctx = OpenGLFrameFifoContext()
        self.gl_ctx.n_720p = 20
        self.gl_ctx.n_1080p = 20
        self.gl_ctx.n_1440p = 20
        self.gl_ctx.n_4K = 20
        self.gl_ctx.n_setup = 20
        self.gl_ctx.n_signal = 20
        self.gl_ctx.flush_when_full = False

        self.glthread = OpenGLThread("glthread", self.gl_ctx)
        self.gl_in_filter = self.glthread.getFrameFilter()

        self.avthread = AVThread("avthread", self.gl_in_filter)
        self.av_in_filter = self.avthread.getFrameFilter()
        # self.live_out_filter =InfoFrameFilter("live_out_filter",self.av_in_filter)
        self.live_out_filter = self.av_in_filter  # skip verbosity

        self.livethread = LiveThread("livethread")

        # Start all threads
        self.glthread.  startCall()
        self.livethread.startCall()
        self.avthread  .startCall()

        if (valkka_xwin):
            # Get an x-window from OpenGLThread once it's been started:
            self.window_id = self.glthread.createWindow(show=False)
            self.pair = WidgetPair(self.w, self.window_id, TestWidget0)
            self.pair.getWidget().setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            self.lay.addWidget(self.pair.getWidget())
        else:
            # Use Qt provided window
            self.video = QtWidgets.QWidget(self.w)
            self.window_id = int(self.video.winId())
            self.video.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            self.lay.addWidget(self.video)

    def closeValkka(self):
        """Stop all valkka threads
        """
        self.avthread  .stopCall()
        self.livethread.stopCall()
        self.glthread.  stopCall()

    def start_streams(self):
        print("start decoding")
        self.avthread.decodingOnCall()  # signal AVThread that it may start decoding

        # define stream source, how the stream is passed on, etc.
        self.ctx = LiveConnectionContext()
        # slot number identifies the stream source
        self.ctx.slot = 1
        self.ctx.connection_type = LiveConnectionType_rtsp  # this is an rtsp connection
        # stream address, i.e. "rtsp://.."
        self.ctx.address = self.stream_address
        # where the received frames are written to.  See filterchain (**)
        self.ctx.framefilter = self.live_out_filter
        # do not attempt to reconnect if stream dies
        self.ctx.msreconnect = 0
        # Timestamp correction type: TimeCorrectionType_none, TimeCorrectionType_dummy, or TimeCorrectionType_smart (default)
        # self.ctx.time_correction=TimeCorrectionType_smart # no need to declare this .. it's the default

        # send the information about the stream to LiveThread
        print("registering stream")
        self.livethread.registerStreamCall(self.ctx)

        # request frames from the stream
        print("playing stream !")
        self.livethread.playStreamCall(self.ctx)

        """
    "Render group" corresponds to an x-window (we can, in principle, render various bitmaps to the same x-window .. this will be implemented in the future (++))
    "Render context" is a mapping from a source (identified by slot number) to a "Render group" (x-window)
    """
        self.glthread.newRenderGroupCall(self.window_id)
        self.context_id = self.glthread.newRenderContextCall(1,               # slot number identifying the stream
                                                             self.window_id,  # where that stream is going to
                                                             # z index of the bitmap (not functional at the moment (++))
                                                             0
                                                             )

        # context_id identifies the Render context
        print("got render context id", self.context_id)

    def stop_streams(self):
        print("stopping streams")
        self.glthread.delRenderContextCall(self.context_id)
        ok = self.glthread.delRenderGroupCall(self.window_id)
        self.avthread.decodingOffCall()

    def closeEvent(self, e):
        print("closeEvent!")
        self.stop_streams()
        self.closeValkka()
        e.accept()


def main():
    if (len(sys.argv) < 2):
        print("Give rtsp stream address, i.e. rtsp://passwd:user@ip")
        return
    app = QtWidgets.QApplication(["single_stream_test"])
    mg = MyGui(stream_address=sys.argv[1])
    mg.show()
    app.exec_()


if (__name__ == "__main__"):
    main()
