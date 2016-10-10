#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
reload(sys)
sys.setdefaultencoding('utf-8')
import operator
import re
from fuzzywuzzy import fuzz


def getIndexKey(wordIndexDict, word):
    if not word.lower() in wordIndexDict:
        wordIndexDict[word.lower()] = len(wordIndexDict)
    return wordIndexDict[word.lower()]


def parseLine(frequencyDict, wordIndexDict, nynorsk_line, bokmaal_line, article_number):
    nn_tokenized = re.findall(r'\w+', nynorsk_line,  re.MULTILINE | re.UNICODE)
    nb_tokenized = re.findall(r'\w+', bokmaal_line,  re.MULTILINE | re.UNICODE)
    consecutive_skips = 0
    for i in range(len(nb_tokenized)):
        if (i >= len(nn_tokenized)):
            break

        # If translation fails, the word is prefixed with '*'
        elif '*' in nb_tokenized[i] or '*' in nn_tokenized[i]:
            continue
        elif nn_tokenized[i] == nb_tokenized[i]:
            continue

        # If the edit distance ratio is lower than 40 % for three consecutive words,
        # we conclude that we have gone astray, and drop the rest of the sentence.
        if (fuzz.ratio(nn_tokenized[i], nb_tokenized[i]) < 40):
            consecutive_skips += 1
            if (consecutive_skips == 3):
                sys.stderr.write("Breaking due to word inconsistency in article number " + str(article_number) + "\n")
                break
        else:
            consecutive_skips = 0

        nn_token_idx = getIndexKey(wordIndexDict, nn_tokenized[i])
        nb_token_idx = getIndexKey(wordIndexDict, nb_tokenized[i])
        if (nn_token_idx, nb_token_idx) in frequencyDict:
            frequencyDict[(nn_token_idx, nb_token_idx)] += 1
        else:
            frequencyDict[(nn_token_idx, nb_token_idx)] = 1


def createDict(frequencyDict, wordIndexDict, nynorsk, bokmaal):
    line_number = 0
    with open(nynorsk, 'r') as nn:
        with open(bokmaal, 'r') as nb:
            while (True):
                line_number += 1
                if line_number % 1000 == 0:
                    sys.stdout.write("Parsing line number " + str(line_number) + "\n")

                nn_line = nn.readline().decode('utf-8')
                nb_line = nb.readline().decode('utf-8')
                if ((nn_line == "" and nb_line != "") or (nn_line != "" and nb_line == "")):
                    raise Exception("Inconsistent file lengths")
                elif (nn_line == "" and nb_line == ""):
                    break
                else:
                    nn_sentences = nn_line.split(".")
                    nb_sentences =  nb_line.split(".")
                    for i in range(len(nb_sentences)):
                        if (i >= len(nn_sentences)):
                            break
                        else:
                            parseLine(frequencyDict, wordIndexDict, nn_sentences[i], nb_sentences[i], line_number)


def writeTranslations(wordIndexDict, frequencyDict, output):
    inv_wordIndexDict = {v: k for k, v in wordIndexDict.items()}
    sorted_freqs = sorted(frequencyDict.items(), key=operator.itemgetter(1), reverse=True)

    with open(output, 'w') as out:
        for freq in sorted_freqs:
            out.write(inv_wordIndexDict[freq[0][0]].encode('utf-8'))
            out.write("¤")
            out.write(inv_wordIndexDict[freq[0][1]].encode('utf-8'))
            out.write("¤")
            out.write(str(freq[1]))
            out.write('\n')


def main():
    frequencyDict = {}
    wordIndexDict = {}
    createDict(frequencyDict, wordIndexDict,  sys.argv[1], sys.argv[2])
    if len(sys.argv) == 5:
        createDict(frequencyDict, wordIndexDict, sys.argv[3], sys.argv[4])

    writeTranslations(wordIndexDict, frequencyDict, "/tmp/outtrans.easy.identity.txt")



if __name__ == '__main__':
    main()