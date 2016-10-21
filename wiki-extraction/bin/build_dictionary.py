#!/usr/bin/env python

import io
import json
import logging
import multiprocessing
import os
import re
import sys
from argparse import ArgumentParser
from collections import Counter
from operator import itemgetter

from nltk.tokenize import sent_tokenize

sys.path.append(os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'lib'))

from apertium import translate


def articles(wiki_json_fn, limit=None):
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
    translations = translate(sents)

    for sent, trans in zip(sents, translations):
        trans_tokens = tokenize(trans)
        tokens = tokenize(sent)

        pairs += compare(tokens, trans_tokens)

    return pairs


class TranslationCounter():
    def __init__(self, source_tf_filter=1, source_df_filter=1.0, trans_tf_filter=1, trans_df_filter=1.0,
                 top_n=None, print_counts=True):
        self.source_tf_filter = source_tf_filter
        self.source_df_filter = source_df_filter
        self.trans_tf_filter = trans_tf_filter
        self.trans_df_filter = trans_df_filter
        self.top_n = top_n
        self.print_counts = print_counts

        self.count_dict = {}
        self.source_tf = Counter()
        self.trans_tf = Counter()
        self.source_df = Counter()
        self.trans_df = Counter()
        self.count_docs = 0

    def _add_to_map(self, pairs):
        for a, b in pairs:
            if a in self.count_dict:
                counter = self.count_dict[a]
                counter.update([b])
            else:
                self.count_dict[a] = Counter([b])

        return self

    def _filtered_trans(self, word):
        return not ((self.trans_tf[word] >= self.trans_tf_filter) and
                    (self.trans_df[word] / float(self.count_docs) <= self.trans_df_filter))

    def _format(self, word, count):
        if self.print_counts:
            return '%s:%d' % (word, count)
        else:
            return word

    def update(self, pairs):
        self.count_docs += 1

        source_tokens, trans_tokens = zip(*pairs)
        self.source_tf.update(source_tokens)
        self.source_df.update(set(source_tokens))
        self.trans_tf.update(trans_tokens)
        self.trans_df.update(set(trans_tokens))

        self._add_to_map(pairs)

    def print(self, f):
        for key, counts in self.count_dict.items():
            if (self.source_tf[key] >= self.source_tf_filter) and \
                    (self.source_df[key] / float(self.count_docs) <= self.source_df_filter):
                candidates = [(v, c) for v, c in counts.items() if not self._filtered_trans(v)]
                candidates = sorted(candidates, key=itemgetter(1), reverse=True)

                if self.top_n:
                    candidates = candidates[:self.top_n]

                f.write(u'%s\t%s\n' % (key, ' '.join([self._format(v, c) for v, c in candidates])))


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
    opts = parser.parse_args()

    n_procs = opts.procs
    limit = None if opts.limit == 0 else opts.limit
    wiki_fn = opts.input_file
    out_fn = opts.output_file

    pool = multiprocessing.Pool(processes=n_procs)

    trans_counter = TranslationCounter(source_tf_filter=opts.source_tf_filter, source_df_filter=opts.source_df_filter,
                                       trans_tf_filter=opts.trans_tf_filter, trans_df_filter=opts.trans_df_filter,
                                       top_n=opts.top_n, print_counts=not opts.supress_counts)

    for pairs in pool.map(article_to_pairs, articles(wiki_fn, limit=limit)):
        trans_counter.update(pairs)

    with io.open(out_fn, mode='w', encoding='utf-8') as f:
        trans_counter.print(f)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    main()
