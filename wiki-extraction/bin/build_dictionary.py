#!/usr/bin/env python

import io
import json
import logging
import multiprocessing
import os
import re
from argparse import ArgumentParser
from collections import Counter

import sys
from nltk.tokenize import sent_tokenize

sys.path.append(os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'lib'))

from apertium import translate


def articles(wiki_json_fn, limit = None):
    count = 0

    with io.open(wiki_json_fn, mode='r', encoding='utf-8') as f:
        for line in f:
            count += 1

            article = json.loads(line)

            yield article

            if limit and count > limit:
                return

            if count % 1000 == 0:
                logging.info("read %d articles" % count)


def tokenize(text):
    return [token.lower() for token in re.findall(r'\w+', text, re.UNICODE | re.MULTILINE)]


def compare(tokens, trans_tokens):
    pairs = []

    same_len = len(tokens) == len(trans_tokens)
    consecutive = False

    for a, b in zip(tokens, trans_tokens):
        if a != b:
            if consecutive and not same_len:
                break

            if not consecutive:
                consecutive = True

            pairs.append((a, b))
        else:
            consecutive = False

    return pairs


def article_to_pairs(article):
    pairs = []
    sents = sent_tokenize(article['text'], language='norwegian')

    for sent in sents:
        trans_tokens = tokenize(translate(sent))
        tokens = tokenize(sent)

        pairs += compare(tokens, trans_tokens)

    return pairs


def add_to_map(m, pairs):
    for a, b in pairs:
        if a in m:
            counter = m[a]
            counter.update([b])
        else:
            m[a] = Counter([b])

    return m



def main():
    parser = ArgumentParser()
    parser.add_argument('-p', '--procs', default=1, type=int)
    parser.add_argument('-l', '--limit', default=0, type=int)
    parser.add_argument('-i', '--input-file')
    parser.add_argument('-o', '--output-file')
    opts = parser.parse_args()

    n_procs = opts.procs
    limit = None if opts.limit == 0 else opts.limit
    wiki_fn = opts.input_file
    out_fn = opts.output_file

    pool = multiprocessing.Pool(processes=n_procs)

    count_dict = {}

    for pairs in pool.map(article_to_pairs, articles(wiki_fn, limit=limit)):
        add_to_map(count_dict, pairs)

    with io.open(out_fn, mode='w', encoding='utf-8') as f:
        for key, counts in count_dict.items():
            f.write(u'%s\t%s\n' % (key, ' '.join(['%s:%s' % (v, c) for v, c in counts.items()])))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    main()