import logging
import subprocess


def translate(sent):
    proc = subprocess.Popen(['apertium', 'nno-nob'],
                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    output, err = proc.communicate(sent.encode('utf-8'))

    if len(err) > 0:
        logging.error("apertium returned error: %s" % err.decode('utf-8', errors='ignore'))

    return output.decode('utf-8')