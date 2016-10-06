#!/usr/bin/env python
# -*- coding: utf-8 -*-

from subprocess import call
import sys

def fetchWiki():
    # Download and extract wikipedia
    # Save as xml file
    call(["fetchWikiDump.sh"])


def preprocessWiki():
    # Parse xml. Save as txt file. One line per document.
    pass


def translateWiki():
    # Translate dump
    call(["apertium", "-f", "txt", "nob-nno", "noinput", "nooutput"])
    call(["apertium", "-f", "txt", "nno-nob", "nninput", "nnoutput"])


def createDic(nninput, nnoutput, noinput, nooutput):
    # Keep track of translations. Create dictionary of type:
    # læreren, læraren
    # ikke, ikkje
    # etc
    pass

def writeDict(dict, output):
    # Write the dictionary to a shared volume.
    pass


def main():
    fetchWiki()
    preprocessWiki()
    translateWiki()
    dict = createDic("nninput", "nnoutput", "noinput", "nooutput")
    writeDict(dict, output=sys.argv[1])


if __name__ == '__main__':
    main()