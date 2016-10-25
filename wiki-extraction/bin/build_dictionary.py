#!/usr/bin/env python

import io
import json
import logging
import multiprocessing
import os
import re
import sys
from argparse import ArgumentParser
from bz2 import BZ2File
from gzip import GzipFile

from future.moves.itertools import repeat
from nltk.tokenize import sent_tokenize

try:
    # noinspection PyShadowingBuiltins,PyUnresolvedReferences
    import itertools.izip as zip
except ImportError:
    pass

sys.path.append(os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'lib'))

from apertium import translate
from translation_counter import TranslationCounter


def articles(wiki_json_fn, limit=None):
    count = 0

    _, ext = os.path.splitext(wiki_json_fn)

    if ext == '.gz':
        f = GzipFile(wiki_json_fn, mode='r')
    elif ext == '.bz2':
        f = BZ2File(wiki_json_fn, mode='r')
    else:
        f = io.open(wiki_json_fn, mode='rb')

    for line in f:
        count += 1

        article = json.loads(line.decode('utf-8'))

        yield article

        if limit and count > limit:
            return

        if count % 10000 == 0:
            logging.info("read %d articles" % count)

    f.close()


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


def article_to_pairs(arg):
    article, direction = arg
    pairs = []

    if 'text' not in article:
        return []

    sents = sent_tokenize(article['text'], language='norwegian')
    translations = translate(sents, direction)

    for sent, trans in zip(sents, translations):
        trans_tokens = tokenize(trans)
        tokens = tokenize(sent)

        pairs += compare(tokens, trans_tokens)

    return pairs


def main():
    parser = ArgumentParser()
    parser.add_argument('-p', '--procs', default=1, type=int)
    parser.add_argument('-l', '--limit', default=0, type=int)
    parser.add_argument('-i', '--input-file')
    parser.add_argument('-o', '--output-file')
    parser.add_argument('-s', '--source-df-filter', default=1.0, type=float)
    parser.add_argument('-t', '--trans-df-filter', default=1.0, type=float)
    parser.add_argument('-S', '--source-tf-filter', default=1, type=int)
    parser.add_argument('-T', '--trans-tf-filter', default=1, type=int)
    parser.add_argument('-n', '--top-n', default=0, type=int)
    parser.add_argument('-C', '--supress-counts', action='store_true')
    parser.add_argument('-d', '--direction', default='nno-nob')
    opts = parser.parse_args()

    n_procs = opts.procs
    limit = None if opts.limit == 0 else opts.limit
    wiki_fn = opts.input_file
    out_fn = opts.output_file
    direction = opts.direction

    pool = multiprocessing.Pool(processes=n_procs)

    trans_counter = TranslationCounter(source_tf_filter=opts.source_tf_filter, source_df_filter=opts.source_df_filter,
                                       trans_tf_filter=opts.trans_tf_filter, trans_df_filter=opts.trans_df_filter,
                                       top_n=opts.top_n, print_counts=not opts.supress_counts)

    for pairs in pool.map(article_to_pairs, zip(articles(wiki_fn, limit=limit), repeat(direction))):
        trans_counter.update(pairs)

    with io.open(out_fn, mode='w', encoding='utf-8') as f:
        trans_counter.print(f)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    main()
