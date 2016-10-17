#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import re
from fuzzywuzzy import fuzz
reload(sys)
sys.setdefaultencoding('utf-8')

def usage():
    print "usage: createSynonymDictionary.py <nynorsk-input> <bokmål-input> (<nynorsk-input> <bokmål-input>) <output>"
    print "<nynorsk-input> and <bokmål-input> should be parallel corpora with same number of lines. One or two parallel corpora is supported as input."


def get_index_key(word_index_dict, word):
    if not word.lower() in word_index_dict:
        word_index_dict[word.lower()] = len(word_index_dict)
    return word_index_dict[word.lower()]


def parse_line(frequency_dict, word_index_dict, nynorsk_line, bokmaal_line):
    nn_tokenized = re.findall(r'\w+', nynorsk_line,  re.MULTILINE | re.UNICODE)
    nb_tokenized = re.findall(r'\w+', bokmaal_line,  re.MULTILINE | re.UNICODE)

    if (len(nn_tokenized) != len(nb_tokenized)):
        # Drop the whole sentence if it doesn't have the same number of tokens.
        return

    consecutive_skips = 0
    for i in range(len(nb_tokenized)):

        # If translation fails, the word is prefixed with '*'
        if '*' in nb_tokenized[i] or '*' in nn_tokenized[i]:
            continue

        # If the edit distance ratio is lower than 40 % for three consecutive words,
        # we conclude that we have gone astray, and drop the rest of the sentence.
        if (fuzz.ratio(nn_tokenized[i], nb_tokenized[i]) < 40):
            consecutive_skips += 1
            if (consecutive_skips == 3):
                break
        else:
            consecutive_skips = 0

        nn_token_idx = get_index_key(word_index_dict, nn_tokenized[i])
        nb_token_idx = get_index_key(word_index_dict, nb_tokenized[i])
        if (nn_token_idx, nb_token_idx) in frequency_dict:
            frequency_dict[(nn_token_idx, nb_token_idx)] += 1
        else:
            frequency_dict[(nn_token_idx, nb_token_idx)] = 1


def parse_corpora(frequency_dict, word_index_dict, nynorsk, bokmaal):
    line_number = 0
    with open(nynorsk, 'r') as nn:
        with open(bokmaal, 'r') as nb:
            while (True):
                line_number += 1
                if line_number % 10000 == 0:
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
                            parse_line(frequency_dict, word_index_dict, nn_sentences[i], nb_sentences[i])


def write_synonym_dictionary(word_index_dict, frequency_dict, output):
    collapsed_dict = get_collapsed_dictionary(frequency_dict)

    inv_word_index_dict = {v: k for k, v in word_index_dict.items()}
    
    with open(output, 'w') as out:
        for collapsed_dict_item in collapsed_dict:
            word_and_freq_dict = collapsed_dict[collapsed_dict_item]

            highest_freq = 0.0
            for word in word_and_freq_dict:
                if word_and_freq_dict[word] > highest_freq:
                    highest_freq = word_and_freq_dict[word]

            # Skip all frequencies below 20.
            if highest_freq < 20:
                continue

            synonyms = [collapsed_dict_item]

            for word in word_and_freq_dict:
                if word_and_freq_dict[word] > highest_freq * 0.3:
                    synonyms.append(word)

            deduplicated_synonyms = list(set(synonyms))
            if len(deduplicated_synonyms) < 2:
                continue

            for i in range(len(deduplicated_synonyms)):
                out.write(inv_word_index_dict[deduplicated_synonyms[i]].encode('utf-8'))
                if (i < len(deduplicated_synonyms) - 1):
                    out.write(",")
            out.write("\n")


def get_collapsed_dictionary(frequency_dict):
    collapsed_dict = {}
    for word_pair in frequency_dict.keys():
        if not word_pair[0] in collapsed_dict:
            collapsed_dict[word_pair[0]] = {}

        word_idx_dict = collapsed_dict[word_pair[0]]
        word_idx_dict[word_pair[1]] = frequency_dict[word_pair]
    return collapsed_dict


def main():
    frequency_dict = {}
    word_index_dict = {}
    if not (len(sys.argv) == 4 or len(sys.argv) == 6):
        usage()
        sys.exit(-1)

    parse_corpora(frequency_dict, word_index_dict, sys.argv[1], sys.argv[2])
    if len(sys.argv) > 3:
        parse_corpora(frequency_dict, word_index_dict, sys.argv[3], sys.argv[4])

    write_synonym_dictionary(word_index_dict, frequency_dict, sys.argv[-1])


if __name__ == '__main__':
    main()