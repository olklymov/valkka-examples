import time, sys
from setproctitle import setproctitle
from valkka.multiprocess import MessageProcess, MessageObject, safe_select
from valkka.api2 import ShmemRGBClient
# from skeleton.singleton import getEventFd, reserveIndex
from skeleton.sync import EventGroup, SyncIndex
from skeleton.singleton import event_fd_group_1


class RGB24Process(MessageProcess):
    """A multiprocess that reads RGB24 frames from shared memory and does something with them

    You can use this process to read several libValkka RGB24 frame servers simultaneouslly

    This class implements the frontend/backend model of multiprocessing (not to be confused with web-apps!)

    ::

        Backend methods (designated with __ or with c__) <=PIPE=> Frontend methods
          Backend reads the pipe and multiplexes                    You just call these
          also any other communication channels                     from your python main process


    Backend is _the_ multiprocess running in its own virtual memory space, isolated from the rest of the processes.

    Intercommunication is handled under-the-hood, making life easier for the API programmer that just calls Frontend methods.

    Backend method can be "normal" or asynchronous python

    In this example we have "normal" (i.e. not asynchronous python) front- and backend
    """
    def __init__(self, mstimeout = 1000):
        super().__init__()
        self.mstimeout = mstimeout
        # events to synchronize some multiprocessing frontend calls
        # with the backend excecution:
        self.eg = EventGroup(100)


    """BACKEND methods

    Never call these methods from the main python process: 
    they are internal for the backend
    """

    def preRun__(self):
        """This should be subclassed for your multiprocess class.  It is executed just after the fork (i.e. in the backend)
        
        Use this to do variable initialization etc. before the async execution starts and for naming your multiprocess
        """    
        print("preRun__")
        # name your multiprocess: now you can easily find it with linux process and memory
        # monitoring tools
        # I recommend using smem and/or htop
        setproctitle("Valkka-example-RGB24Process")
        self.client_by_fd = {}
        self.shmem_pars_by_slot = {}


    def postRun__(self):
        """Last thing executed before multiprocess exits
        """
        print("postRun__")


    # backend methods: do not call these from the frontend 
    # (i.e. from the main python process)
    
    def readPipes__(self, timeout):
        """Multiplex all intercom pipes / events

        This is used by your multiprocesses run() method
        (which you don't need to touch)

        Multiplexing file-descriptor is actually more neat in asyncio: 
        see the fragmp4 process

        For a tutorial for multiplexing communication pipes and sockets
        in normal (not asyncio) python, see: https://docs.python.org/3/howto/sockets.html
        """
        rlis = [self.back_pipe]
        # self.back_pipe is the intercom pipe with the main python process
        # listen to all rgb frame sources
        frame_fds = list(self.client_by_fd.keys())

        rlis += frame_fds
        
        rs, ws, es = safe_select(rlis, [], [], timeout = timeout)

        # rs is a list of event file descriptors that have been triggered
        for fd in rs:
            # 1. handle the main intercom pipe
            if fd == self.back_pipe:
                self.handleBackPipe__(self.back_pipe)
            # 2. handle frame coming from libValkka c++ side
            if fd in frame_fds:
                client = self.client_by_fd[fd]
                index, meta = client.pullFrame()
                if (index == None):
                    print("RGB24Process: handleFrame__ : weird.. rgb client got none")
                else:
                    data = client.shmem_list[index][0:meta.size]
                    data = data.reshape((meta.height, meta.width, 3))
                    self.handleFrame__(data, meta)


    def handleFrame__(self, frame, meta):
        print("RGB24Process: handleFrame__ : rgb client got frame", frame.shape, "from slot", meta.slot)
        """metadata has the following members:
        size 
        width
        height
        slot
        mstimestamp
        """
        # send a message to the main process like this:
        self.send_out__({"results from" : "RGB24Process"})


    # commands that come from the main python process (aka frontend)
    def c__activateRGB24Client(self, 
            name = None, 
            n_ringbuffer = None, 
            width = None , 
            height = None,
            ipc_index = None
            ):
        """This will activate a shared memory client that reads RGB24 frames
        from shared memory libValkka c++ side (as defined in your filterchain)
        """
        print("c__activateRGB24Client called with", name, n_ringbuffer, width, height)
        client = ShmemRGBClient(
            name = name,
            n_ringbuffer = n_ringbuffer,
            width = width,
            height = height,
            mstimeout = self.mstimeout,
            verbose = False
        )
        # eventfd = getEventFd(ipc_index)
        eventfd = event_fd_group_1.fromIndex(ipc_index)
        client.useEventFd(eventfd) # do not forget!
        # let's get a posix file descriptor, i.e. a plain integer:
        fd = eventfd.getFd()
        self.client_by_fd[fd] = client
        

    def c__deactivateRGB24Client(self,
        ipc_index = None,
        event_index = None
        ):
        # eventfd = getEventFd(ipc_index)
        eventfd = event_fd_group_1.fromIndex(ipc_index)
        # let's get a posix file descriptor, i.e. a plain integer
        fd = eventfd.getFd()
        try:
            self.client_by_fd.pop(fd)
        except KeyError:
            print("c__deactivateRGB24Client : no client at ipc_index", ipc_index)
        # inform multiprocessing frontend (= main python process)
        # that this command has been finalized:
        self.eg.set(event_index)


    def c__customCall(self, parameter = 1):
        """The backend part of some custom call

        In asyncio, always encapsulate your methods with try/except
        """
        try:
            print("some asynchronous custom call with parameter", parameter)
        except Exception as e:
            print("c__customCall failed with", e)


    """FRONTEND
    
    These methods are called by your main python process
    """

    def activateRGB24Client(self, 
            name = None,
            n_ringbuffer = None,
            width = None,
            height = None,
            ipc_index = None
        ):
        """Tells process to start getting frames from libValkka cpp side
        """
        self.sendMessageToBack(MessageObject(
            "activateRGB24Client",
            name = name,
            n_ringbuffer = n_ringbuffer,
            width = width,
            height = height,
            ipc_index = ipc_index
        ))
        # that intercommunicates with backend and looks
        # for method "c__activateMP4Client" there in
        # in a more realistic application, fmp4 clients
        # are activated, based on the websocket server
        # callbacks (as client connects to your websocket server)
        # in the backend only


    def deactivateRGB24Client(self, ipc_index):
        """This frontend method returns only after the backend 
        method "c__deactivateRGB24Client" exits.

        It's a good idea to do this, for example, when adding/removing rgb shmem
        servers and clients.  

        This is done using the SyncIndex context manager:
        """
        with SyncIndex(self.eg) as i:
            # this section exits once the backend
            # call is ready
            self.sendMessageToBack(MessageObject(
                "deactivateRGB24Client",
                ipc_index = ipc_index,
                event_index = i
            ))
        print("deactivateRGB24Client OK", ipc_index)


    def customCall(self, parameter = 1):
        # your demo custom call :)
        self.sendMessageToBack(MessageObject(
            "customCall",
            parameter = parameter
        ))
        # that intercommunicates with backend and looks
        # for method "c__customCall" there in


def test1():
    p = RGB24Process()
    p.start()
    time.sleep(1)
    print("sending activate")
    # ipc_index = reserveIndex()
    ipc_index, eventfd = event_fd_group_1.reserve()

    p.activateRGB24Client(
        name = "kokkelis",
        n_ringbuffer = 10,
        width = 100,
        height = 200,
        ipc_index = ipc_index
    )
    time.sleep(1)
    print("sending deactivate")
    p.deactivateRGB24Client(
        ipc_index = ipc_index
    )
    print("exiting")
    p.stop()
    print("bye!")


if __name__ == "__main__":
    test1()

