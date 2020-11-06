"""This module has the version number.  Automatically changed with the "setver.bash" script.  Don't touch!
"""
VERSION_MAJOR=1
VERSION_MINOR=0
VERSION_PATCH=0

def getVersionTag():
    return "(%i.%i.%i)" % (VERSION_MAJOR, VERSION_MINOR, VERSION_PATCH)

