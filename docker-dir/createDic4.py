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
    def __init__(self, aligned_words):
        self.aligned_words = aligned_words

    def sentence_prob(self):
        score = 0.0
        for word in self.aligned_words:
            score += math.log(word.distance)
        return score

    def isAstray(self):
        if len(self.aligned_words) > 3:
            if self.sentence_prob() < -len(self.aligned_words):
                return True
        return False


class AlignedWord:

    def __init__(self, nn_word, nb_word, distance):
        self.nn_word = nn_word
        self.nb_word = nb_word
        self.distance = distance


class Word:
    def __init__(self, startIdx, endIdx, token):
        self.startIdx = startIdx
        self.endIdx = endIdx
        self.token = token


def computeAlignments(words_tail1, words_tail2, aligned_words, aligned_sentences):
    if (len(words_tail1) == 0) and len(words_tail2) == 0:
        #Sucess - base case!
        aligned_sentences.append(AlignedSentence(aligned_words))
        return
    if (len(words_tail1) == 0 and len(words_tail2) != 0) or (len(words_tail1) != 0 and len(words_tail2) == 0):
        #Failure
        return

    if (len(words_tail1) > (len(words_tail2) * 2) + 1) or len(words_tail2) > (len(words_tail1) * 2 + 1):
        # Early failure, will not succeed.
        return

    if len(words_tail1) >= 1 and len(words_tail2) >= 1:
        seq_copy = aligned_words[:]

        #seq_copy.append(str(words_tail1[0]) + "->" + str(words_tail2[0]))
        word = AlignedWord(words_tail1[0], words_tail2[0], 1)
        seq_copy.append(word)
        if (AlignedSentence(seq_copy).isAstray()):
            # Failure
            return
        computeAlignments(words_tail1[2:], words_tail2[2:], seq_copy, aligned_sentences)

        if len(words_tail1) > 1:
            seq_copy2 = aligned_words[:]

            seq_copy2.append(str(words_tail1[1]) + "->" + str(words_tail2[0]))
            #word = AlignedWord(words_tail1[0], words_tail2[0], 1)

            computeAlignments(words_tail1[4:], words_tail2[2:], seq_copy2, aligned_sentences)

        if len(words_tail2) > 1:
            seq_copy3 = aligned_words[:]
            seq_copy3.append(str(words_tail1[0]) + "->" + str(words_tail2[1]))
            computeAlignments(words_tail1[2:], words_tail2[4:], seq_copy3, aligned_sentences)



def getAlignments(nn_tokenized, nb_tokenized):
    nn_words = []
    for perm in sequence.getPermutations(len(nn_tokenized)):
        startIdx = perm[0]
        endIdx = perm[1]
        nn_words.append(Word(nn_tokenized[startIdx:endIdx], startIdx, endIdx))

    nb_words = []
    for perm in sequence.getPermutations(len(nb_tokenized)):
        startIdx = perm[0]
        endIdx = perm[1]
        nb_words.append(Word(nb_tokenized[startIdx:endIdx], startIdx, endIdx))

    aligned_words = []
    aligned_sentences = []

    computeAlignments(nn_words, nb_words, aligned_words, aligned_sentences)


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


def writeDictionary(wordIndexDict, frequencyDict, output):
    collapsed_dict = get_collapsed_dictionary(frequencyDict)


    inv_wordIndexDict = {v: k for k, v in wordIndexDict.items()}
    with open(output, 'w') as out:
        for collapsed_dict_item in collapsed_dict:
            word_and_freq_dict = collapsed_dict[collapsed_dict_item]

            highest_freq = 0.0
            for word in word_and_freq_dict:
                if word_and_freq_dict[word] > highest_freq:
                    highest_freq = word_and_freq_dict[word]

            if highest_freq < 50:
                continue

            synonyms = []
            synonyms.append(collapsed_dict_item)

            for word in word_and_freq_dict:
                if word_and_freq_dict[word] > highest_freq * 0.3:
                    synonyms.append(word)

            deduplicated_synonyms = list(set(synonyms))
            if len(deduplicated_synonyms) < 2:
                continue

            for i in range(len(deduplicated_synonyms)):
                out.write(inv_wordIndexDict[deduplicated_synonyms[i]].encode('utf-8'))
                if (i < len(deduplicated_synonyms) - 1):
                    out.write(",")
            out.write("\n")


def get_collapsed_dictionary(frequencyDict):
    collapsed_dict = {}
    for word_pair in frequencyDict.keys():
        if not word_pair[0] in collapsed_dict:
            collapsed_dict[word_pair[0]] = {}

        word_idx_dict = collapsed_dict[word_pair[0]]
        word_idx_dict[word_pair[1]] = frequencyDict[word_pair]
    return collapsed_dict


def main():
    frequencyDict = {}
    wordIndexDict = {}
    createDict(frequencyDict, wordIndexDict,  sys.argv[1], sys.argv[2])
    if len(sys.argv) == 5:
        createDict(frequencyDict, wordIndexDict, sys.argv[3], sys.argv[4])

    writeDictionary(wordIndexDict, frequencyDict, "/tmp/dict.3.txt")


if __name__ == '__main__':
    main()