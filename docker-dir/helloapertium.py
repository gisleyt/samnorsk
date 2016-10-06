#!/usr/bin/env python
# -*- coding: utf-8 -*-

from subprocess import call
import sys

def main():
    with open("noinput", 'w') as f:
        f.write("Jeg skriver bokmål.")

    output = sys.argv[1] + "/nooutput.txt"
    call(["apertium", "-f", "txt", "nob-nno", "noinput", output])

if __name__ == '__main__':
    main()