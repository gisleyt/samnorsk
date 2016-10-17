#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys

reload(sys)
sys.setdefaultencoding('utf-8')
import operator
import re
import math
from fuzzywuzzy import fuzz
import sequence


def getIndexKey(wordIndexDict, word):
    if not word.lower() in wordIndexDict:
        wordIndexDict[word.lower()] = len(wordIndexDict)
    return wordIndexDict[word.lower()]


class AlignedSentence:

    max_probability = {}

    def __init__(self, aligned_words):
        self.aligned_words = aligned_words

    def sentence_prob(self):
        score = 0.0
        for word in self.aligned_words:
            score += math.log(word.distance)
        return score

    def isAstray(self):
        if len(self.aligned_words) > 3:
            sent_prob = self.sentence_prob()
            if len(self.aligned_words) in self.max_probability:
                if self.max_probability[len(self.aligned_words)] > sent_prob:
                    return True
                else:
                    self.max_probability[len(self.aligned_words)] = sent_prob
                    return False
            else:
                self.max_probability[len(self.aligned_words)] = sent_prob
                return False
        return False


class AlignedWord:
    def __init__(self, nn_word, nb_word):
        self.nn_word = nn_word
        self.nb_word = nb_word
        score = 1
        for v in nn_word.token:
            for w in nb_word.token:
                score *= max((fuzz.ratio(v, w) / 100.0), 0.1)
        self.distance = score


class Word:
    def __init__(self, startIdx, endIdx, token):
        self.startIdx = startIdx
        self.endIdx = endIdx
        self.token = token

    def __str__(self):
        return str(self.token) + "<" + str(self.startIdx) + ":" + str(self.endIdx) + ">"


def parseLine(frequencyDict, wordIndexDict, nynorsk_line, bokmaal_line, article_number):
    nynorsk_line = nynorsk_line.replace("*", "")
    bokmaal_line = bokmaal_line.replace("*", "")

    nn_tokenized = re.findall(r'\w+', nynorsk_line,  re.MULTILINE | re.UNICODE)
    nb_tokenized = re.findall(r'\w+', bokmaal_line,  re.MULTILINE | re.UNICODE)

    AlignedSentence.max_probability = {}

    aligned = get_best_alignment(nn_tokenized, nb_tokenized)

    if (aligned != None):
        #print "Sucesse"
        for aligned_word in aligned.aligned_words:
            nn_token_idx = getIndexKey(wordIndexDict, " ".join(aligned_word.nn_word.token))
            nb_token_idx = getIndexKey(wordIndexDict, " ".join(aligned_word.nb_word.token))
            if (nn_token_idx, nb_token_idx) in frequencyDict:
                frequencyDict[(nn_token_idx, nb_token_idx)] += 1
            else:
                frequencyDict[(nn_token_idx, nb_token_idx)] = 1
    else:
        print "Rejected NN(" + str(nn_tokenized) + ") NB( " + str(nb_tokenized) + " )"




def createDict(frequencyDict, wordIndexDict, nynorsk, bokmaal):
    line_number = 0
    with open(nynorsk, 'r') as nn:
        with open(bokmaal, 'r') as nb:
            while (True):
                line_number += 1
                if line_number % 10 == 0:
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


def computeAlignments(words_tail1, words_tail2, aligned_words, aligned_sentences):
    if (len(words_tail1) == 0) and len(words_tail2) == 0:
        # Sucess - base case!
        sentence = AlignedSentence(aligned_words)
        aligned_sentences.append(sentence)
        return
    if (len(words_tail1) == 0 and len(words_tail2) != 0) or (len(words_tail1) != 0 and len(words_tail2) == 0):
        # Failure
        return

    if (len(words_tail1) > (len(words_tail2) * 2) + 1) or len(words_tail2) > (len(words_tail1) * 2 + 1):
        # Early failure, will not succeed.
        return

    if len(words_tail1) >= 1 and len(words_tail2) >= 1:
        seq_copy = aligned_words[:]


        if (AlignedSentence(seq_copy).isAstray()):
            # Failure
            return

        # seq_copy.append(str(words_tail1[0]) + "->" + str(words_tail2[0]))
        word = AlignedWord(words_tail1[0], words_tail2[0])
        seq_copy.append(word)

        computeAlignments(words_tail1[2:], words_tail2[2:], seq_copy, aligned_sentences)

        if len(words_tail1) > 1:
            seq_copy2 = aligned_words[:]
            seq_copy2.append(AlignedWord(words_tail1[1], words_tail2[0]))
            computeAlignments(words_tail1[4:], words_tail2[2:], seq_copy2, aligned_sentences)

        if len(words_tail2) > 1:
            seq_copy3 = aligned_words[:]
            seq_copy3.append(AlignedWord(words_tail1[0], words_tail2[1]))
            computeAlignments(words_tail1[2:], words_tail2[4:], seq_copy3, aligned_sentences)


def get_best_alignment(nn_tokenized, nb_tokenized):
    max_score = -100000
    best_sentence = None
    for aligned in getAlignments(nn_tokenized, nb_tokenized):
        if aligned.sentence_prob() > max_score:
            max_score = aligned.sentence_prob()
            best_sentence = aligned

    return best_sentence

def getAlignments(nn_tokenized, nb_tokenized):
    nn_words = []
    for perm in sequence.getPermutations2(len(nn_tokenized)):
        startIdx = perm[0]
        endIdx = perm[1]
        nn_words.append(Word(startIdx, endIdx, nn_tokenized[startIdx:endIdx]))

    nb_words = []
    for perm in sequence.getPermutations2(len(nb_tokenized)):
        startIdx = perm[0]
        endIdx = perm[1]
        nb_words.append(Word(startIdx, endIdx, nb_tokenized[startIdx:endIdx]))

    aligned_words = []
    aligned_sentences = []
    computeAlignments(nn_words, nb_words, aligned_words, aligned_sentences)
    return aligned_sentences


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


def main2():
    nn = """Namnet Sekken har ikkje
    noko
    med
    ein
    sekk
    å
    gjere, men
    kjem
    frå
    norrønt / sæ - kinn /, som
    tyder
    noko
    slikt
    som «det
    bratte
    landet
    som
    stig
    opp
    frå
    sjøen»."""

    nb = """ Navnet Sekken har ingenting med en sekk å gjøre, men kommer fra norrønt /*sæ-kinn/, som betyr noe slikt som «det bratte landet som bestiger fra sjøen»"""

    nn_tokenized = re.findall(r'\w+', nn, re.MULTILINE | re.UNICODE)
    nb_tokenized = re.findall(r'\w+', nb, re.MULTILINE | re.UNICODE)

    for word in get_best_alignment(nn_tokenized, nb_tokenized).aligned_words:
        print str(word.nb_word)  + " " + str(word.nn_word)



def main():
    frequencyDict = {}
    wordIndexDict = {}
    createDict(frequencyDict, wordIndexDict, sys.argv[1], sys.argv[2])
    if len(sys.argv) == 5:
        createDict(frequencyDict, wordIndexDict, sys.argv[3], sys.argv[4])

    writeTranslations(wordIndexDict, frequencyDict, "/tmp/smart.out.txt")


    #nb = ["Jeg", "visste", "ikke", "om", "de", "tingene", "du", "snakker", "om"]
    #nn = ["Eg", "visste", "ingen", "ting", "om", "desse", "tinga", "du", "snakkar", "om"]



    #max_score = -100000
    #best_sentence = None
    #for aligned in getAlignments(nn, nb):
    #    if aligned.sentence_prob() > max_score:
    #        max_score = aligned.sentence_prob()
    #        best_sentence = aligned

    #print "SENTENCE " + str(aligned.sentence_prob())
    #for word in best_sentence.aligned_words:
    #    print str(word.nb_word)  + " " + str(word.nn_word)


if __name__ == '__main__':
    main()